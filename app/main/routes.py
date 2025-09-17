## app/main/routes.py

from flask import (Blueprint, render_template, jsonify, request, redirect,
                   url_for, flash, current_app)
from sqlalchemy import func
from sqlalchemy.orm import joinedload 

from datetime import datetime, timezone
from collections import defaultdict

from app import db, socketio
from flask_login import current_user, login_required
from app.models.models import (Part, StatusHistory, AuditLog, RouteTemplate,
                               RouteStage, Stage, PartNote, Permission, StatusType)
from app.admin.forms import ConfirmStageQuantityForm, AddNoteForm, AddChildPartForm
from app.services import query_service
from app.utils import to_safe_key

main = Blueprint('main', __name__)


def _send_websocket_notification(event_type: str, message: str, part_id: str = None):
    """Централизованная функция для отправки WebSocket-уведомлений."""
    try:
        data = {'event': event_type, 'message': message}
        if part_id:
            data['part_id'] = part_id
            # Генерируем URL, чтобы уведомление было кликабельным
            data['url'] = url_for('main.history', part_id=part_id, _external=False)
        socketio.emit('notification', data)
    except RuntimeError:
        current_app.logger.info("WebSocket emit skipped: Not in a Socket.IO server context.")


@main.route('/')
def dashboard():
    """
    Главная страница (панель мониторинга).
    Отображает сводную информацию по всем изделиям.
    """
    # Запрос выбирает только "корневые" детали (которые не являются дочерними ни для кого)
    product_progress_query = db.session.query(
        Part.product_designation,
        func.count(Part.part_id).label('total_parts'),
        func.sum(Part.quantity_total).label('total_quantity'),
        func.sum(Part.quantity_completed).label('completed_quantity')
    ).filter(~Part.parent_associations.any()).group_by(Part.product_designation).all()

    products = [{
        'product_designation': row.product_designation,
        'total_parts': row.total_parts,
        'total_possible_stages': row.total_quantity or 0,
        'total_completed_stages': row.completed_quantity or 0
    } for row in product_progress_query]

    return render_template('dashboard.html', products=products)


@main.route('/api/parts/<path:product_designation>')
def api_parts_for_product(product_designation):
    """
    API-эндпоинт для динамической загрузки списка деталей для изделия с фильтрацией.
    """
    query = Part.query.options(
        joinedload(Part.route_template).joinedload(RouteTemplate.stages).joinedload(RouteStage.stage),
        joinedload(Part.responsible)
    ).filter(
        Part.product_designation == product_designation,
        ~Part.parent_associations.any() # Только верхнеуровневые детали
    )

    # Динамическая фильтрация и поиск
    search_term = request.args.get('search')
    if search_term:
        search_filter = f"%{search_term}%"
        query = query.filter(
            db.or_(
                Part.part_id.ilike(search_filter),
                Part.name.ilike(search_filter),
                Part.material.ilike(search_filter)
            )
        )
    
    responsible_id = request.args.get('responsible_id')
    if responsible_id and responsible_id.isdigit():
        query = query.filter(Part.responsible_id == int(responsible_id))

    parts_from_query = query.order_by(Part.part_id.asc()).all()

    parts_list = []
    for part in parts_from_query:
        route_stages_data = []
        if part.route_template:
            completed_quantities = defaultdict(int)
            for h in part.history:
                if h.status_type == StatusType.COMPLETED:
                    completed_quantities[h.status] += h.quantity

            ordered_stages = sorted(part.route_template.stages, key=lambda s: s.order)
            
            for rs in ordered_stages:
                stage_name = rs.stage.name
                qty_done = completed_quantities.get(stage_name, 0)
                status = 'pending'

                if qty_done >= part.quantity_total: status = 'completed'
                elif qty_done > 0: status = 'in_progress'

                route_stages_data.append({'name': stage_name, 'status': status, 'qty_done': qty_done})
        
        parts_list.append({
            'part_id': part.part_id, 'name': part.name, 'material': part.material, 'size': part.size,
            'current_status': part.current_status, 'creation_date': part.date_added.strftime('%Y-%m-%d'),
            'quantity_completed': part.quantity_completed, 'quantity_total': part.quantity_total,
            'history_url': url_for('main.history', part_id=part.part_id),
            'route_stages': route_stages_data,
            'delete_url': url_for('admin.part.delete_part', part_id=part.part_id),
            'edit_url': url_for('admin.part.edit_part', part_id=part.part_id),
            'qr_url': url_for('admin.part.generate_single_qr', part_id=part.part_id),
            'responsible_user': part.responsible.username if part.responsible else 'Не назначен'
        })

    permissions = {
        'can_delete': current_user.can(Permission.DELETE_PARTS),
        'can_edit': current_user.can(Permission.EDIT_PARTS),
        'can_generate_qr': current_user.can(Permission.GENERATE_QR)
    } if current_user.is_authenticated else None

    return jsonify({'parts': parts_list, 'permissions': permissions})


@main.route('/history/<path:part_id>')
def history(part_id):
    """Страница с полной историей одной детали."""
    part = db.get_or_404(Part, part_id)
    combined_history = query_service.get_combined_history(part)
    note_form = AddNoteForm()
    child_form = AddChildPartForm()

    if part.route_template:
        note_form.stage.query = db.session.query(Stage).join(RouteStage).filter(
            RouteStage.template_id == part.route_template_id
        ).order_by(Stage.name)
    else:
        note_form.stage.query = db.session.query(Stage).filter_by(id=-1)

    return render_template(
        'history.html', part=part, combined_history=combined_history,
        note_form=note_form, child_form=child_form
    )


@main.route('/scan/<path:part_id>')
def select_stage(part_id):
    """Страница, открывающаяся после сканирования QR-кода."""
    part = db.get_or_404(Part, part_id)
    if not part.route_template:
        flash('Ошибка: Этой детали не присвоен технологический маршрут.', 'error')
        return redirect(url_for('main.dashboard'))

    completed_quantities = defaultdict(int)
    for h in part.history:
        if h.status_type == StatusType.COMPLETED:
            completed_quantities[h.status] += h.quantity
        
    ordered_stages = sorted(part.route_template.stages, key=lambda s: s.order)
    next_stage_obj = None
    for rs in ordered_stages:
        if completed_quantities.get(rs.stage.name, 0) < part.quantity_total:
            next_stage_obj = rs.stage
            break

    form = ConfirmStageQuantityForm()
    if next_stage_obj and form.quantity.data is None:
        completed_on_this_stage = completed_quantities.get(next_stage_obj.name, 0)
        remaining = part.quantity_total - completed_on_this_stage
        form.quantity.data = remaining if remaining > 0 else 1

    return render_template(
        'select_stage.html', part=part, next_stage=next_stage_obj, form=form
    )


@main.route('/confirm_stage/<path:part_id>/<int:stage_id>', methods=['POST'])
def confirm_stage(part_id, stage_id):
    """ОБНОВЛЕНО: Обрабатывает подтверждение, брак и переделку."""
    part = db.get_or_404(Part, part_id)
    stage = db.get_or_404(Stage, stage_id)
    form = ConfirmStageQuantityForm()

    if form.validate_on_submit():
        quantity_done = form.quantity.data
        action_type = form.action.data
        
        completed_on_this_stage = db.session.query(func.sum(StatusHistory.quantity)).filter_by(part_id=part.part_id, status=stage.name, status_type=StatusType.COMPLETED).scalar() or 0
        remaining_on_stage = part.quantity_total - completed_on_this_stage
        
        if quantity_done > remaining_on_stage and action_type == 'completed':
            flash(f'Ошибка: Нельзя выполнить {quantity_done} шт. На этом этапе осталось {remaining_on_stage} шт.', 'error')
            return redirect(url_for('main.select_stage', part_id=part.part_id))

        new_history = StatusHistory(
            part_id=part_id, status=stage.name,
            operator_name=form.operator_name.data,
            quantity=quantity_done,
            status_type=StatusType(action_type)
        )
        db.session.add(new_history)

        part.last_update = datetime.now(timezone.utc)
        notification_message = ""

        if action_type == 'scrapped':
            part.quantity_scrapped = (part.quantity_scrapped or 0) + quantity_done
            notification_message = f"Забраковано {quantity_done} шт. детали {part.part_id}."
            flash(notification_message, "error")
        else: # 'completed'
            part.current_status = stage.name
            
            # Пересчет общего прогресса
            all_history = StatusHistory.query.filter_by(part_id=part.part_id, status_type=StatusType.COMPLETED).all()
            completed_quantities = defaultdict(int)
            for h in all_history: completed_quantities[h.status] += h.quantity
            
            stage_names = [rs.stage.name for rs in sorted(part.route_template.stages, key=lambda s: s.order)]
            min_completed = part.quantity_total
            for stage_name in stage_names:
                qty = completed_quantities.get(stage_name, 0)
                if qty < min_completed: min_completed = qty
            part.quantity_completed = min_completed
            
            notification_message = f"Деталь {part_id} перешла на этап '{stage.name}'. Готово: {quantity_done} шт."
            flash(notification_message, "success")

        db.session.commit()

        socketio.emit('update_dashboard', {
            'part_id': part.part_id, 'new_status': part.current_status,
            'quantity_completed': part.quantity_completed, 'quantity_total': part.quantity_total,
            'product_designation': part.product_designation,
            'safe_key': to_safe_key(part.product_designation)
        })

        _send_websocket_notification('stage_completed', notification_message, part.part_id)
        
        return redirect(url_for('main.dashboard'))

    return render_template('select_stage.html', part=part, next_stage=stage, form=form)


@main.route('/add_note/<path:part_id>', methods=['POST'])
@login_required
def add_note(part_id):
    part = db.get_or_404(Part, part_id)
    form = AddNoteForm()
    if part.route_template:
        form.stage.query = db.session.query(Stage).join(RouteStage).filter(
            RouteStage.template_id == part.route_template_id
        ).order_by(Stage.name)
    else:
        form.stage.query = db.session.query(Stage).filter_by(id=-1)

    if form.validate_on_submit():
        stage_obj = form.stage.data
        new_note = PartNote(part_id=part.part_id, user_id=current_user.id,
                            text=form.text.data, stage_id=stage_obj.id if stage_obj else None)
        db.session.add(new_note)

        log_details = f"К детали '{part.part_id}' добавлено примечание."
        log_entry = AuditLog(user_id=current_user.id, action="Добавлено примечание",
                             details=log_details, category='part', part_id=part.part_id)
        db.session.add(log_entry)
        db.session.commit()
        flash('Примечание успешно добавлено.', 'success')
    else:
        error_messages = [e for field, errors in form.errors.items() for e in errors]
        flash('Ошибка: ' + ' '.join(error_messages), 'error')
    return redirect(url_for('main.history', part_id=part.part_id))


@main.route('/edit_note/<int:note_id>', methods=['POST'])
@login_required
def edit_note(note_id):
    note = db.get_or_404(PartNote, note_id)
    if note.user_id != current_user.id and not current_user.is_admin():
        return jsonify({'status': 'error', 'message': 'Нет прав'}), 403

    new_text = request.form.get('text')
    if new_text and new_text.strip():
        note.text = new_text
        log_details = f"В детали '{note.part_id}' изменено примечание (ID: {note.id})."
        log_entry = AuditLog(user_id=current_user.id, action="Изменено примечание",
                             details=log_details, category='management', part_id=note.part_id)
        db.session.add(log_entry)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Примечание обновлено.', 'new_text': new_text})
    else:
        return jsonify({'status': 'error', 'message': 'Текст не может быть пустым.'}), 400


@main.route('/delete_note/<int:note_id>', methods=['POST'])
@login_required
def delete_note(note_id):
    note = db.get_or_404(PartNote, note_id)
    if note.user_id != current_user.id and not current_user.is_admin():
        flash('У вас нет прав для удаления этого примечания.', 'error')
        return redirect(url_for('main.history', part_id=note.part_id))

    part_id = note.part_id
    log_details = f"В детали '{part_id}' удалено примечание (ID: {note.id})."
    log_entry = AuditLog(user_id=current_user.id, action="Удалено примечание",
                         details=log_details, category='management', part_id=part_id)
    db.session.add(log_entry)

    db.session.delete(note)
    db.session.commit()
    flash('Примечание удалено.', 'success')
    return redirect(url_for('main.history', part_id=part_id))