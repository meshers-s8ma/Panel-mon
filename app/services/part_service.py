# app/services/part_service.py

import os
import io
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
from PIL import Image
import pandas as pd
from flask import current_app
from collections import defaultdict
from sqlalchemy.exc import IntegrityError

from app import db, socketio
from app.models.models import (Part, AuditLog, RouteTemplate, ResponsibleHistory,
                               StatusHistory, Stage, RouteStage, AssemblyComponent)
from app.utils import generate_qr_code_as_base64


def _send_websocket_notification(event_type: str, message: str, part_id: str = None):
    """
    Централизованная функция для отправки WebSocket-уведомлений.
    Обернута в try...except для безопасного вызова вне веб-контекста.
    """
    try:
        data = {'event': event_type, 'message': message}
        if part_id:
            data['part_id'] = part_id
        socketio.emit('notification', data)
    except RuntimeError:
        current_app.logger.info("WebSocket emit skipped: Not in a Socket.IO server context.")


def save_part_drawing(file_storage, config):
    """
    Безопасно сохраняет файл чертежа, сжимая его, и возвращает уникальное имя.
    """
    filename = secure_filename(file_storage.filename)
    unique_filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{filename}"
    file_path = os.path.join(config['DRAWING_UPLOAD_FOLDER'], unique_filename)

    try:
        img = Image.open(file_storage)
        img.save(file_path, optimize=True, quality=85)
        return unique_filename
    except Exception:
        file_storage.seek(0)
        file_storage.save(file_path)
        return unique_filename


def create_single_part(form, user, config):
    """
    Создает одну деталь на основе данных из формы.
    """
    drawing_filename = None
    if form.drawing.data:
        drawing_filename = save_part_drawing(form.drawing.data, config)
    
    new_part = Part(
        part_id=form.part_id.data,
        product_designation=form.product.data,
        name=form.name.data,
        material=form.material.data,
        size=form.size.data,
        route_template_id=form.route_template.data,
        drawing_filename=drawing_filename,
        quantity_total=form.quantity_total.data
    )
    db.session.add(new_part)
    
    log_entry = AuditLog(part_id=new_part.part_id, user_id=user.id, action="Создание", details="Деталь создана вручную.", category='part')
    db.session.add(log_entry)
    db.session.commit()
    
    _send_websocket_notification(
        'part_created',
        f"Пользователь {user.username} создал деталь: {new_part.part_id}",
        new_part.part_id
    )


def import_parts_from_excel(file_storage, user, config):
    """
    ОБНОВЛЕНО: Обрабатывает иерархические Excel/CSV, создавая связи "многие-ко-многим".
    Использует массовые операции для повышения производительности.
    """
    filename = file_storage.filename
    
    try:
        file_storage.seek(0, os.SEEK_END)
        if file_storage.tell() == 0:
            return 0, 0
        file_storage.seek(0)

        if filename.endswith('.csv'):
            df = pd.read_csv(file_storage, header=None, dtype=str, skip_blank_lines=True)
        elif filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file_storage, header=None, engine='openpyxl', dtype=str)
        else:
            raise ValueError("Неподдерживаемый формат файла.")
    except Exception as e:
        current_app.logger.error(f"Failed to read file {filename}: {e}", exc_info=True)
        raise ValueError(f"Не удалось прочитать файл. Убедитесь, что он не поврежден.")

    df.dropna(how='all', inplace=True)
    if df.empty: return 0, 0

    header_row_index = df[df.apply(lambda row: row.astype(str).str.contains('Обозначение').any(), axis=1)].index.min()
    if pd.isna(header_row_index):
        raise ValueError("В файле не найдена строка с заголовками (ожидается колонка 'Обозначение').")

    product_df = df.iloc[:header_row_index]
    product_name_values = [str(cell).strip() for _, row in product_df.iterrows() for cell in row.values if pd.notna(cell) and str(cell).strip()]
    current_product_designation = product_name_values[0] if product_name_values else "Без названия"

    df.columns = [str(col).strip() for col in df.iloc[header_row_index]]
    df = df.iloc[header_row_index + 1:].reset_index(drop=True)

    default_route = RouteTemplate.query.filter_by(is_default=True).first()
    if not default_route:
        raise ValueError("Не найден маршрут по умолчанию. Пожалуйста, создайте его в 'Управлении маршрутами'.")

    parts_to_create = {}
    parent_child_map = defaultdict(list)
    current_parent_id = None

    for index, row in df.iterrows():
        part_id = str(row.get("Обозначение", "")).strip()
        name = str(row.get("Наименование", "")).strip()
        is_parent_row = part_id and (not name or name.lower() == 'nan')
        is_data_row = part_id and name and name.lower() != 'nan'

        if is_parent_row:
            current_parent_id = part_id
            if part_id not in parts_to_create:
                parts_to_create[part_id] = {
                    'product_designation': current_product_designation,
                    'name': f"Сборка {part_id}", 'material': "Сборка", 'quantity_total': 1,
                    'route_template_id': default_route.id, 'size': ''
                }
            continue

        if is_data_row:
            if part_id in parts_to_create: continue
            
            material = str(row.get("Прим.", "Не указан")).strip()
            if not material or material.lower() == 'nan': material = "Не указан"
            quantity_str = str(row.get("Кол-во", "1")).strip()
            quantity = int(float(quantity_str)) if quantity_str and quantity_str.lower() != 'nan' else 1
            operations_str = str(row.get("Операции", "")).strip()
            route_template_id = _get_or_create_route_from_operations(operations_str).id
            size = str(row.get("Размер", "")).strip()
            if size.lower() == 'nan': size = ""
            
            parts_to_create[part_id] = {
                'product_designation': current_product_designation, 'name': name,
                'quantity_total': 1, 'size': size, 'material': material,
                'route_template_id': route_template_id
            }
            if current_parent_id:
                parent_child_map[current_parent_id].append({'child_id': part_id, 'quantity': quantity})
    
    existing_part_ids = {p[0] for p in db.session.query(Part.part_id).filter(Part.part_id.in_(parts_to_create.keys()))}
    
    new_parts, new_components, audit_logs = [], [], []
    added_count, skipped_count = 0, 0

    for part_id, data in parts_to_create.items():
        if part_id in existing_part_ids:
            skipped_count += 1
            continue
        new_parts.append(Part(part_id=part_id, **data))
        audit_logs.append(AuditLog(part_id=part_id, user_id=user.id, action="Создание", details=f"Импорт из файла {filename}.", category='part'))
        added_count += 1
    
    if new_parts: db.session.bulk_save_objects(new_parts)
    if audit_logs: db.session.bulk_save_objects(audit_logs)

    for parent_id, children in parent_child_map.items():
        if parent_id in existing_part_ids: continue
        for child_data in children:
            if child_data['child_id'] in existing_part_ids: continue
            new_components.append(AssemblyComponent(parent_id=parent_id, **child_data))

    if new_components: db.session.bulk_save_objects(new_components)
    db.session.commit()

    if added_count > 0:
        _send_websocket_notification('import_finished', f"Пользователь {user.username} импортировал {added_count} новых записей.")
    
    return added_count, skipped_count


def _get_or_create_route_from_operations(operations_str: str) -> RouteTemplate:
    if not operations_str or operations_str.lower() == 'nan':
        default_route = RouteTemplate.query.filter_by(is_default=True).first()
        if not default_route:
            raise ValueError("Не найден маршрут по умолчанию для деталей без указания операций.")
        return default_route
    operations = [op.strip() for op in operations_str.split(',') if op.strip()]
    if not operations:
        return _get_or_create_route_from_operations("")
    route_name = " -> ".join(operations)
    route = RouteTemplate.query.filter_by(name=route_name).first()
    if route:
        return route
    new_route = RouteTemplate(name=route_name, is_default=False)
    db.session.add(new_route)
    db.session.flush()
    for i, op_name in enumerate(operations):
        stage = Stage.query.filter(Stage.name.ilike(op_name)).first()
        if not stage:
            stage = Stage(name=op_name)
            db.session.add(stage)
            db.session.flush()
        route_stage = RouteStage(template_id=new_route.id, stage_id=stage.id, order=i)
        db.session.add(route_stage)
    return new_route


def update_part_from_form(part, form, user, config):
    changes = []
    if part.product_designation != form.product_designation.data:
        changes.append(f"Изделие: '{part.product_designation}' -> '{form.product_designation.data}'")
        part.product_designation = form.product_designation.data
    if hasattr(form, 'name') and part.name != form.name.data:
        changes.append(f"Наименование: '{part.name}' -> '{form.name.data}'")
        part.name = form.name.data
    if hasattr(form, 'material') and part.material != form.material.data:
        changes.append(f"Материал: '{part.material}' -> '{form.material.data}'")
        part.material = form.material.data
    if hasattr(form, 'size') and part.size != form.size.data:
        changes.append(f"Размер: '{part.size}' -> '{form.size.data}'")
        part.size = form.size.data
    if form.drawing.data:
        if part.drawing_filename:
            old_file_path = os.path.join(config['DRAWING_UPLOAD_FOLDER'], part.drawing_filename)
            if os.path.exists(old_file_path): os.remove(old_file_path)
        part.drawing_filename = save_part_drawing(form.drawing.data, config)
        changes.append("Обновлен чертеж.")
    if changes:
        log_details = "; ".join(changes)
        log_entry = AuditLog(part_id=part.part_id, user_id=user.id, action="Редактирование", details=log_details, category='part')
        db.session.add(log_entry)
        db.session.commit()
        _send_websocket_notification('part_updated', f"Пользователь {user.username} обновил данные детали {part.part_id}", part.part_id)


def delete_single_part(part, user, config):
    part_id = part.part_id
    if part.drawing_filename:
        file_path = os.path.join(config['DRAWING_UPLOAD_FOLDER'], part.drawing_filename)
        if os.path.exists(file_path): os.remove(file_path)
    log_entry = AuditLog(part_id=part_id, user_id=user.id, action="Удаление", details=f"Деталь '{part_id}' и вся ее история были удалены.", category='part')
    db.session.add(log_entry)
    db.session.delete(part)
    db.session.commit()
    _send_websocket_notification('part_deleted', f"Пользователь {user.username} удалил деталь: {part_id}", part_id)


def change_part_route(part, new_route, user):
    if part.route_template_id != new_route.id:
        old_route_name = part.route_template.name if part.route_template else "Не назначен"
        part.route_template_id = new_route.id
        log_details = f"Маршрут изменен с '{old_route_name}' на '{new_route.name}'."
        log_entry = AuditLog(part_id=part.part_id, user_id=user.id, action="Редактирование", details=log_details, category='part')
        db.session.add(log_entry)
        db.session.commit()
        _send_websocket_notification('part_updated', f"Для детали {part.part_id} изменен маршрут.", part.part_id)
        return True
    return False


def change_responsible_user(part, new_user, current_user):
    old_responsible_id = part.responsible_id
    new_responsible_id = new_user.id if new_user else None
    if old_responsible_id != new_responsible_id:
        old_user_name = part.responsible.username if part.responsible else "Не назначен"
        new_user_name = new_user.username if new_user else "Не назначен"
        part.responsible_id = new_responsible_id
        db.session.add(ResponsibleHistory(part_id=part.part_id, user_id=new_responsible_id))
        log_details = f"Ответственный изменен с '{old_user_name}' на '{new_user_name}'."
        log_entry = AuditLog(part_id=part.part_id, user_id=current_user.id, action="Смена ответственного", details=log_details, category='management')
        db.session.add(log_entry)
        db.session.commit()
        _send_websocket_notification('part_updated', f"Для детали {part.part_id} сменен ответственный.", part.part_id)
        return True
    return False


def create_child_part(form, parent_part_id, user):
    """ОБНОВЛЕНО: Создает дочернюю деталь и связь AssemblyComponent."""
    parent_part = db.session.get(Part, parent_part_id)
    if not parent_part:
        raise ValueError(f"Родительская деталь с ID {parent_part_id} не найдена.")
    
    # Сначала создаем саму деталь
    new_part = Part(
        part_id=form.part_id.data,
        product_designation=parent_part.product_designation,
        name=form.name.data,
        material=form.material.data,
        quantity_total=1, # Количество дочерней детали всегда 1
        route_template_id=parent_part.route_template_id
    )
    db.session.add(new_part)
    
    # Затем создаем связь "многие-ко-многим"
    component_link = AssemblyComponent(
        parent_id=parent_part_id,
        child_id=form.part_id.data,
        quantity=form.quantity_total.data # Здесь количество в составе родителя
    )
    db.session.add(component_link)

    log_details = f"В состав '{parent_part.name}' добавлен узел '{new_part.name}' ({form.quantity_total.data} шт.)."
    db.session.add(AuditLog(part_id=parent_part_id, user_id=user.id, action="Обновление состава", details=log_details, category='part'))
    
    db.session.commit()
    
    _send_websocket_notification('part_updated', f"В состав изделия {parent_part.part_id} добавлен новый узел.", parent_part.part_id)


def log_qr_generation(part_id, user):
    log_entry = AuditLog(part_id=part_id, user_id=user.id, action="Генерация QR", details=f"Создан QR-код для детали '{part_id}'.", category='part')
    db.session.add(log_entry)
    db.session.commit()


def get_parts_for_printing(part_ids):
    parts = Part.query.filter(Part.part_id.in_(part_ids)).all()
    return [{'part': part, 'qr_image': generate_qr_code_as_base64(part.part_id)} for part in parts]


def cancel_stage_by_history_id(history_id, user):
    history_entry = db.get_or_404(StatusHistory, history_id)
    part = history_entry.part
    stage_name = history_entry.status
    log_details = f"Отменен этап: '{stage_name}' ({history_entry.quantity} шт.)."
    db.session.add(AuditLog(part_id=part.part_id, user_id=user.id, action="Отмена этапа", details=log_details, category='part'))
    db.session.delete(history_entry)
    db.session.flush()
    if part.route_template:
        ordered_stages = sorted(part.route_template.stages, key=lambda s: s.order)
        stage_names = [rs.stage.name for rs in ordered_stages]
        all_history = StatusHistory.query.filter_by(part_id=part.part_id).all()
        completed_quantities = defaultdict(int)
        for h in all_history:
            completed_quantities[h.status] += h.quantity
        min_completed = part.quantity_total
        for s_name in stage_names:
            qty = completed_quantities.get(s_name, 0)
            if qty < min_completed:
                min_completed = qty
        part.quantity_completed = min_completed
    else:
        part.quantity_completed = 0
    new_last_history = StatusHistory.query.filter_by(part_id=part.part_id).order_by(StatusHistory.timestamp.desc()).first()
    part.current_status = new_last_history.status if new_last_history else 'На складе'
    db.session.commit()
    _send_websocket_notification('part_updated', f"Для детали {part.part_id} отменен этап '{stage_name}'.", part.part_id)
    return part, stage_name


def delete_multiple_parts(part_ids, user, config):
    parts_to_delete = Part.query.filter(Part.part_id.in_(part_ids)).all()
    deleted_count = 0
    for part in parts_to_delete:
        if part.drawing_filename:
            file_path = os.path.join(config['DRAWING_UPLOAD_FOLDER'], part.drawing_filename)
            if os.path.exists(file_path): os.remove(file_path)
        db.session.add(AuditLog(part_id=part.part_id, user_id=user.id, action="Массовое удаление", details=f"Деталь '{part.part_id}' удалена.", category='part'))
        db.session.delete(part)
        deleted_count += 1
    db.session.commit()
    if deleted_count > 0:
        _send_websocket_notification('bulk_delete', f"Пользователь {user.username} удалил {deleted_count} деталей.")
    return deleted_count