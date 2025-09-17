# tests/test_part_service.py

import pytest
import io
from unittest.mock import patch, MagicMock
from werkzeug.datastructures import FileStorage

from app import db
from app.services import part_service
from app.models.models import Part, RouteTemplate, Stage, User, StatusHistory, AuditLog


@pytest.fixture
def mock_csv_file():
    """Создает фикстуру с "моковым" CSV-файлом в памяти."""
    csv_content = (
        '"","Наборка №3","","","","",""\n'
        '"№","Обозначение","Наименование","Кол-во","Размер","Операции","Прим."\n'
        '"","АСЦБ-000475","","","","",""\n'
        '"","ЦДСА.8АТ-9800.00.03.000СБ","Палец","1","","Пок",""\n'
        '"","ЦДСА.218.79.00.04","Болт осевой","5","S24х530(1)","Св,HRC","30ХГСА"\n'
    )
    file_storage = FileStorage(
        stream=io.BytesIO(csv_content.encode('utf-8')),
        filename="test_import.csv",
        content_type="text/csv"
    )
    return file_storage

@pytest.fixture
def mock_empty_file():
    """Создает фикстуру с пустым файлом."""
    file_storage = FileStorage(
        stream=io.BytesIO(b''),
        filename="empty.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return file_storage


class TestPartService:
    """Тесты для сервиса, отвечающего за бизнес-логику деталей."""

    def test_import_from_hierarchical_csv(self, database, mock_csv_file):
        """Тест: Проверяет импорт из иерархического CSV-файла."""
        admin_user = User.query.filter_by(username='admin').first()
        
        added_count, skipped_count = part_service.import_parts_from_excel(
            mock_csv_file, admin_user, {}
        )
        
        assert added_count == 3
        assert skipped_count == 0
        parent = db.session.get(Part, "АСЦБ-000475")
        child1 = db.session.get(Part, "ЦДСА.8АТ-9800.00.03.000СБ")
        assert parent is not None
        assert child1 is not None
        assert child1.parent_id == parent.part_id

    def test_import_from_empty_file(self, database, mock_empty_file):
        """Тест: Импорт из пустого файла должен завершаться без ошибок и возвращать 0."""
        admin_user = User.query.filter_by(username='admin').first()
        added, skipped = part_service.import_parts_from_excel(mock_empty_file, admin_user, {})
        assert added == 0
        assert skipped == 0

    def test_import_unsupported_format_raises_error(self, database):
        """Тест: Импорт файла неподдерживаемого формата вызывает ValueError."""
        admin_user = User.query.filter_by(username='admin').first()
        unsupported_file = FileStorage(stream=io.BytesIO(b'test data'), filename='test.txt')
        # Ожидаем общее сообщение об ошибке, которое возвращает сервис
        with pytest.raises(ValueError, match="Не удалось прочитать файл. Убедитесь, что он не поврежден."):
            part_service.import_parts_from_excel(unsupported_file, admin_user, {})

    @patch('app.services.part_service.socketio.emit')
    def test_websocket_notification_on_create(self, mock_emit, database):
        """Тест: Проверяет, что при создании детали отправляется WebSocket-уведомление."""
        admin_user = User.query.filter_by(username='admin').first()
        mock_form = MagicMock()
        mock_form.part_id.data = "NEW-001"
        mock_form.product.data = "Новое Изделие"
        mock_form.name.data = "Новая Деталь"
        mock_form.material.data = "Титан"
        mock_form.size.data = "10x10"
        mock_form.route_template.data = RouteTemplate.query.first().id
        mock_form.quantity_total.data = 10
        mock_form.drawing.data = None

        part_service.create_single_part(mock_form, admin_user, {})
        
        mock_emit.assert_called_once()

    def test_import_from_malformed_csv_handles_error(self, database):
        """Тест: Проверяет корректную обработку ошибки при отсутствии заголовков в CSV."""
        csv_content = '"Поле1","Поле2"\n"Значение1","Значение2"'
        malformed_file = FileStorage(
            stream=io.BytesIO(csv_content.encode('utf-8')),
            filename="malformed.csv", content_type="text/csv"
        )
        admin_user = User.query.filter_by(username='admin').first()
        with pytest.raises(ValueError, match="В файле не найдена строка с заголовками"):
            part_service.import_parts_from_excel(malformed_file, admin_user, {})

    def test_delete_single_part(self, database):
        """Тест: Проверяет удаление одной детали и создание записи в логе."""
        admin_user = User.query.filter_by(username='admin').first()
        part_to_delete = db.session.get(Part, 'TEST-001')
        assert part_to_delete is not None
        part_service.delete_single_part(part_to_delete, admin_user, {'DRAWING_UPLOAD_FOLDER': '/tmp'})
        assert db.session.get(Part, 'TEST-001') is None
        assert AuditLog.query.filter_by(part_id='TEST-001', action='Удаление').first() is not None

    def test_change_part_route(self, database):
        """Тест: Проверяет смену технологического маршрута для детали."""
        admin_user = User.query.filter_by(username='admin').first()
        part = db.session.get(Part, 'TEST-001')
        new_route = RouteTemplate(name='Новый Тестовый Маршрут')
        db.session.add(new_route)
        db.session.commit()
        changed = part_service.change_part_route(part, new_route, admin_user)
        assert changed is True
        assert part.route_template_id == new_route.id
        
    def test_cancel_stage(self, database):
        """Тест: Проверяет отмену пройденного этапа и пересчет прогресса."""
        admin_user = User.query.filter_by(username='admin').first()
        part = db.session.get(Part, 'TEST-001')
        stage = Stage.query.filter_by(name='Резка').first()
        history_entry = StatusHistory(part_id='TEST-001', status=stage.name, operator_name='Оператор', quantity=1)
        part.quantity_completed = 1
        db.session.add(history_entry)
        db.session.commit()
        assert part.quantity_completed == 1
        part_service.cancel_stage_by_history_id(history_entry.id, admin_user)
        assert part.quantity_completed == 0
        assert db.session.get(StatusHistory, history_entry.id) is None

    def test_import_fails_if_no_default_route(self, database, mock_csv_file):
        """Тест: Импорт должен завершиться с ошибкой, если в БД нет маршрута по умолчанию."""
        admin_user = User.query.filter_by(username='admin').first()
        RouteTemplate.query.filter_by(is_default=True).delete()
        db.session.commit()
        with pytest.raises(ValueError, match="Не найден маршрут по умолчанию"):
            part_service.import_parts_from_excel(mock_csv_file, admin_user, {})