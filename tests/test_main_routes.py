# tests/test_main_routes.py

import pytest
from flask import url_for
from app.models.models import Part, Stage, RouteTemplate, RouteStage, StatusHistory, PartNote, User
from app import db

class TestCoreWorkflow:
    """Группа тестов для проверки основного рабочего процесса."""

    def test_scan_and_confirm_stage_workflow(self, client, database):
        """Тест: Проверяет полный цикл прохождения всех этапов детали."""
        part = db.session.get(Part, 'TEST-001')
        assert part is not None
        
        # Получаем этапы в правильном порядке из связанной модели
        stages_in_order = [rs.stage for rs in sorted(part.route_template.stages, key=lambda rs: rs.order)]
        
        for stage in stages_in_order:
            client.post(
                url_for('main.confirm_stage', part_id='TEST-001', stage_id=stage.id),
                data={'operator_name': 'Tester', 'quantity': 1}
            )
        
        part_final = db.session.get(Part, 'TEST-001')
        assert part_final.quantity_completed == 1
        assert StatusHistory.query.filter_by(part_id='TEST-001').count() == len(stages_in_order)

    def test_select_stage_page_shows_correct_form(self, client, database):
        """Тест: Страница /scan/ корректно отображает следующий этап."""
        response = client.get(url_for('main.select_stage', part_id='TEST-001'))
        assert response.status_code == 200
        # Проверяем, что на странице есть название первого этапа ("Резка")
        assert 'Резка'.encode('utf-8') in response.data

    def test_history_page_loads(self, client, database):
        """Тест: Страница истории детали загружается успешно."""
        response = client.get(url_for('main.history', part_id='TEST-001'))
        assert response.status_code == 200
        assert 'История: TEST-001'.encode('utf-8') in response.data

    def test_api_parts_for_product_returns_json(self, client, database):
        """Тест: API-эндпоинт для деталей возвращает корректный JSON."""
        response = client.get(url_for('main.api_parts_for_product', product_designation='Тестовое изделие'))
        assert response.status_code == 200
        assert response.is_json
        data = response.get_json()
        assert len(data['parts']) == 1
        assert data['parts'][0]['part_id'] == 'TEST-001'

    def test_scan_part_with_no_route_fails_gracefully(self, client, database):
        """Тест: Сканирование детали без маршрута показывает корректную ошибку."""
        part_no_route = Part(part_id='NO-ROUTE-001', product_designation='Test', name='Test', material='-')
        db.session.add(part_no_route)
        db.session.commit()
        response = client.get(url_for('main.select_stage', part_id='NO-ROUTE-001'), follow_redirects=True)
        assert response.status_code == 200
        assert 'Этой детали не присвоен технологический маршрут'.encode('utf-8') in response.data

    def test_scan_completed_part_shows_completed_message(self, client, database):
        """Тест: Сканирование полностью готовой детали показывает сообщение о завершении."""
        part = db.session.get(Part, 'TEST-001')
        stages_in_order = [rs.stage for rs in sorted(part.route_template.stages, key=lambda rs: rs.order)]
        for stage in stages_in_order:
            db.session.add(StatusHistory(part_id=part.part_id, status=stage.name, operator_name='Op', quantity=part.quantity_total))
        db.session.commit()
        
        response = client.get(url_for('main.select_stage', part_id='TEST-001'))
        assert response.status_code == 200
        assert 'Все этапы завершены'.encode('utf-8') in response.data


class TestNoteAndHistoryRoutes:
    """Тесты для полного покрытия функционала примечаний."""

    def test_add_note_successfully(self, client, auth_client, database):
        client = auth_client('admin', 'password123')
        response = client.post(url_for('main.add_note', part_id='TEST-001'), data={'text': 'Test Note'})
        assert response.status_code == 302
        assert PartNote.query.count() == 1

    def test_add_empty_note_fails(self, client, auth_client, database):
        client = auth_client('admin', 'password123')
        response = client.post(url_for('main.add_note', part_id='TEST-001'), data={'text': ''}, follow_redirects=True)
        assert response.status_code == 200
        assert 'Ошибка: This field is required.'.encode('utf-8') in response.data

    def test_edit_own_note(self, client, auth_client, database):
        admin = User.query.filter_by(username='admin').first()
        client = auth_client('admin', 'password123')
        note = PartNote(part_id='TEST-001', user_id=admin.id, text='Original')
        db.session.add(note)
        db.session.commit()
        
        response = client.post(url_for('main.edit_note', note_id=note.id), data={'text': 'Updated'})
        assert response.status_code == 200
        db.session.refresh(note)
        assert note.text == 'Updated'

    def test_user_cannot_edit_others_note(self, client, auth_client, database):
        admin = User.query.filter_by(username='admin').first()
        note = PartNote(part_id='TEST-001', user_id=admin.id, text='Original')
        db.session.add(note)
        db.session.commit()

        client = auth_client('manager', 'password123')
        response = client.post(url_for('main.edit_note', note_id=note.id), data={'text': 'Attempt'})
        assert response.status_code == 403
        db.session.refresh(note)
        assert note.text == 'Original'

    def test_delete_note(self, client, auth_client, database):
        admin = User.query.filter_by(username='admin').first()
        client = auth_client('admin', 'password123')
        note = PartNote(part_id='TEST-001', user_id=admin.id, text='To Delete')
        db.session.add(note)
        db.session.commit()
        note_id = note.id
        
        client.post(url_for('main.delete_note', note_id=note_id))
        assert db.session.get(PartNote, note_id) is None