# tests/test_admin_part_routes.py

import os
from flask import url_for
from app import db
from app.models.models import Part, User, Role, RouteTemplate, StatusHistory

class TestAdminPartRoutesSuccess:
    """Тесты для успешных сценариев, выполняемых администратором."""

    def test_part_full_crud(self, client, auth_client, database):
        client = auth_client('admin', 'password123')
        route = RouteTemplate.query.first()
        
        client.post(url_for('admin.part.add_single_part'), data={
            'product': 'P', 'part_id': 'P1', 'name': 'N', 'material': 'M', 
            'route_template': route.id, 'quantity_total': 1
        })
        part = db.session.get(Part, 'P1')
        assert part is not None
        
        client.post(url_for('admin.part.edit_part', part_id='P1'), data={
            'name': 'N2', 'product_designation': 'P', 'material': 'M'
        })
        db.session.refresh(part)
        assert part.name == 'N2'
        
        client.post(url_for('admin.part.delete_part', part_id='P1'))
        assert db.session.get(Part, 'P1') is None

    def test_add_child_part(self, client, auth_client, database):
        client = auth_client('admin', 'password123')
        parent_id = 'TEST-001'
        client.post(url_for('admin.part.add_child_part', parent_part_id=parent_id), data={
            'part_id': 'CHILD-01', 'name': 'Child Part', 'material': 'M', 'quantity_total': 1
        })
        child = db.session.get(Part, 'CHILD-01')
        assert child is not None
        assert child.parent_id == parent_id

    def test_part_actions(self, client, auth_client, database):
        client = auth_client('admin', 'password123')
        part = db.session.get(Part, 'TEST-001')
        new_route = RouteTemplate(name="New Route")
        db.session.add(new_route)
        db.session.commit()
        
        client.post(url_for('admin.part.change_part_route', part_id=part.part_id), data={'new_route': new_route.id})
        db.session.refresh(part)
        assert part.route_template_id == new_route.id
        
        manager = User.query.filter_by(username='manager').first()
        client.post(url_for('admin.part.change_responsible', part_id=part.part_id), data={'responsible': manager.id})
        db.session.refresh(part)
        assert part.responsible_id == manager.id

    def test_cancel_stage(self, client, auth_client, database):
        client = auth_client('admin', 'password123')
        part = db.session.get(Part, 'TEST-001')
        history_entry = StatusHistory(part_id=part.part_id, status='Резка', operator_name='Op', quantity=1)
        db.session.add(history_entry)
        db.session.commit()
        
        client.post(url_for('admin.part.cancel_stage', history_id=history_entry.id))
        assert db.session.get(StatusHistory, history_entry.id) is None

    def test_bulk_actions(self, client, auth_client, database):
        client = auth_client('admin', 'password123')
        
        response_print = client.post(url_for('admin.part.qr_print_preview'), data={'part_ids': ['TEST-001']})
        assert response_print.status_code == 200
        assert b'TEST-001' in response_print.data
        
        client.post(url_for('admin.part.bulk_action'), data={'action': 'delete', 'part_ids': ['TEST-001']})
        assert db.session.get(Part, 'TEST-001') is None

    def test_serve_drawing_file(self, app, client, auth_client, database):
        client = auth_client('admin', 'password123')
        part = db.session.get(Part, 'TEST-001')
        
        drawing_dir = app.config['DRAWING_UPLOAD_FOLDER']
        if not os.path.exists(drawing_dir): os.makedirs(drawing_dir)
        dummy_filename = "test_drawing.jpg"
        dummy_filepath = os.path.join(drawing_dir, dummy_filename)
        with open(dummy_filepath, "w") as f: f.write("dummy content")
        
        part.drawing_filename = dummy_filename
        db.session.commit()

        response = client.get(url_for('admin.part.serve_drawing', filename=dummy_filename))
        assert response.status_code == 200
        assert response.data == b"dummy content"
        os.remove(dummy_filepath)

    def test_change_responsible_form_loads(self, client, auth_client, database):
        client = auth_client('admin', 'password123')
        response = client.get(url_for('admin.part.change_responsible_form', part_id='TEST-001'))
        assert response.status_code == 200
        assert 'Назначить ответственного' in response.data.decode('utf-8')

class TestPartRoutesUnhappyPaths:

    def test_add_part_validation_error(self, client, auth_client, database):
        client = auth_client('admin', 'password123')
        route = RouteTemplate.query.first()
        response = client.post(
            url_for('admin.part.add_single_part'), 
            data={'product': 'P', 'part_id': '', 'name': 'N', 'material': 'M', 'route_template': route.id, 'quantity_total': 1},
            follow_redirects=True
        )
        assert response.status_code == 200
        assert 'Ошибка в поле &#39;Обозначение (Артикул)&#39;: This field is required.' in response.data.decode('utf-8')

    def test_add_existing_part_fails(self, client, auth_client, database):
        client = auth_client('admin', 'password123')
        route = RouteTemplate.query.first()
        response = client.post(
            url_for('admin.part.add_single_part'),
            data={'product': 'P', 'part_id': 'TEST-001', 'name': 'N', 'material': 'M', 'route_template': route.id, 'quantity_total': 1},
            follow_redirects=True
        )
        assert response.status_code == 200
        assert 'Ошибка: Деталь TEST-001 уже существует!' in response.data.decode('utf-8')
    
    # --- НАЧАЛО ИСПРАВЛЕНИЯ: Переписанный тест ---
    def test_add_duplicate_child_part_fails(self, client, auth_client, database):
        """Тест: Нельзя добавить дочерний узел с уже существующим ID."""
        client = auth_client('admin', 'password123')
        
        # 1. Создаем отдельную деталь, которая будет "родителем"
        parent_part = Part(part_id='PARENT-01', product_designation='Test', name='Parent', material='M')
        # 2. Создаем отдельную деталь, которая будет "дубликатом"
        existing_part = Part(part_id='EXISTING-01', product_designation='Test', name='Existing', material='M')
        db.session.add_all([parent_part, existing_part])
        db.session.commit()

        # 3. Пытаемся добавить к PARENT-01 дочернюю деталь с ID EXISTING-01
        response = client.post(
            url_for('admin.part.add_child_part', parent_part_id='PARENT-01'), 
            data={'part_id': 'EXISTING-01', 'name': 'Child', 'material': 'M', 'quantity_total': 1}, 
            follow_redirects=True
        )

        # 4. Проверяем, что получили правильное flash-сообщение
        assert response.status_code == 200
        assert "Ошибка: Деталь с артикулом 'EXISTING-01' уже существует!" in response.data.decode('utf-8')
    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

    def test_bulk_action_with_no_parts_selected(self, client, auth_client, database):
        client = auth_client('admin', 'password123')
        response = client.post(
            url_for('admin.part.bulk_action'),
            data={'action': 'delete', 'part_ids': []},
            follow_redirects=True
        )
        assert response.status_code == 200
        assert 'Вы не выбрали ни одной детали.' in response.data.decode('utf-8')

    def test_bulk_print_with_no_parts_selected(self, client, auth_client, database):
        client = auth_client('admin', 'password123')
        response = client.post(url_for('admin.part.qr_print_preview'), data={'part_ids': []}, follow_redirects=True)
        assert response.status_code == 200
        assert 'Вы не выбрали ни одной детали для печати.' in response.data.decode('utf-8')

    def test_operator_cannot_access_part_routes(self, client, auth_client, database):
        client = auth_client('operator', 'password123')
        
        response_add = client.post(url_for('admin.part.add_single_part'), data={}, follow_redirects=True)
        assert 'У вас нет прав для доступа к этой странице.' in response_add.data.decode('utf-8')
        
        response_edit = client.get(url_for('admin.part.edit_part', part_id='TEST-001'), follow_redirects=True)
        assert 'У вас нет прав для доступа к этой странице.' in response_edit.data.decode('utf-8')
        
        response_delete = client.post(url_for('admin.part.delete_part', part_id='TEST-001'), follow_redirects=True)
        assert 'У вас нет прав для доступа к этой странице.' in response_delete.data.decode('utf-8')
        assert db.session.get(Part, 'TEST-001') is not None