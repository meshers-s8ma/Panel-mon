# tests/test_note_management.py
import pytest
from flask import url_for
from app.models.models import Part, User, PartNote
from app import db

class TestNoteManagement:
    """Тесты для управления примечаниями к детали."""

    def test_add_note_successfully(self, client, auth_client, database):
        """Тест: Аутентифицированный пользователь может добавить примечание."""
        client = auth_client('admin', 'password123')
        response = client.post(url_for('main.add_note', part_id='TEST-001'), data={'text': 'Test Note'})
        assert response.status_code == 302
        assert PartNote.query.count() == 1
        note = PartNote.query.first()
        assert note.text == 'Test Note'

    def test_add_empty_note_fails(self, client, auth_client, database):
        """Тест: Нельзя добавить пустое примечание."""
        client = auth_client('admin', 'password123')
        response = client.post(url_for('main.add_note', part_id='TEST-001'), data={'text': ''}, follow_redirects=True)
        assert response.status_code == 200
        assert 'Ошибка: This field is required.'.encode('utf-8') in response.data
        assert PartNote.query.count() == 0

    def test_edit_own_note_successfully(self, client, auth_client, database):
        """Тест: Пользователь может редактировать собственное примечание."""
        admin = User.query.filter_by(username='admin').first()
        client = auth_client('admin', 'password123')
        note = PartNote(part_id='TEST-001', user_id=admin.id, text='Original')
        db.session.add(note)
        db.session.commit()
        
        response = client.post(url_for('main.edit_note', note_id=note.id), data={'text': 'Updated'})
        assert response.status_code == 200
        assert response.get_json()['status'] == 'success'
        db.session.refresh(note)
        assert note.text == 'Updated'

    def test_delete_own_note_successfully(self, client, auth_client, database):
        """Тест: Пользователь может удалить собственное примечание."""
        admin = User.query.filter_by(username='admin').first()
        client = auth_client('admin', 'password123')
        note = PartNote(part_id='TEST-001', user_id=admin.id, text='To be deleted')
        db.session.add(note)
        db.session.commit()
        note_id = note.id
        
        response = client.post(url_for('main.delete_note', note_id=note_id))
        assert response.status_code == 302
        assert db.session.get(PartNote, note_id) is None