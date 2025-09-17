# tests/test_admin_report_routes.py

from flask import url_for
from unittest.mock import patch
from io import BytesIO
from app.models.models import StatusHistory, Part
from app import db
import datetime

class TestReportRoutes:
    """Тесты для страниц и API отчетов."""

    def test_report_pages_load(self, client, auth_client, database):
        """Тест: Все страницы отчетов успешно загружаются для пользователя с правами."""
        client = auth_client('manager', 'password123') # У менеджера есть доступ к отчетам
        assert client.get(url_for('admin.report.reports_index')).status_code == 200
        assert client.get(url_for('admin.report.report_operator_performance')).status_code == 200
        assert client.get(url_for('admin.report.report_stage_duration')).status_code == 200
        assert client.get(url_for('admin.report.generate_from_cloud')).status_code == 200

    @patch('app.services.graph_service.download_file_from_onedrive')
    @patch('app.services.graph_service.read_row_from_excel_bytes')
    @patch('app.services.document_service.generate_word_from_data')
    def test_generate_from_cloud_success(self, mock_generate_word, mock_read_excel, mock_download, client, auth_client, database):
        """Тест: Проверяет успешный сценарий генерации отчета из облачного файла."""
        client = auth_client('admin', 'password123')
        mock_download.return_value = b'fake excel data'
        mock_read_excel.return_value = {'{{№ бирки}}': 'TEST-123'}
        mock_generate_word.return_value = BytesIO(b'fake word data')
        
        data = {
            'excel_path': '/test.xlsx',
            'row_number': 2,
            'word_template': (BytesIO(b'template'), 'template.docx')
        }
        response = client.post(url_for('admin.report.generate_from_cloud'), data=data)
        assert response.status_code == 200
        assert response.mimetype == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

    @patch('app.services.graph_service.download_file_from_onedrive', side_effect=FileNotFoundError("Mocked Not Found"))
    def test_generate_from_cloud_file_not_found_error(self, mock_download, client, auth_client, database):
        """Тест: Проверяет корректную обработку ошибки, когда файл не найден в OneDrive."""
        client = auth_client('admin', 'password123')
        data = {
            'excel_path': '/bad.xlsx', 'row_number': 2, 'word_template': (BytesIO(b't'), 't.docx')
        }
        response = client.post(url_for('admin.report.generate_from_cloud'), data=data, follow_redirects=True)
        assert response.status_code == 200
        assert 'Файл не найден в OneDrive'.encode('utf-8') in response.data

    def test_api_operator_performance(self, client, auth_client, database):
        """Тест: API для производительности операторов возвращает корректный JSON."""
        client = auth_client('manager', 'password123')
        
        # Добавляем тестовые данные в историю
        db.session.add(StatusHistory(part_id='TEST-001', status='Test', operator_name='Иванов', quantity=1))
        db.session.commit()

        response = client.get(url_for('admin.report.api_report_operator_performance'))
        assert response.status_code == 200
        assert response.is_json
        data = response.get_json()
        assert 'labels' in data
        assert 'datasets' in data
        assert data['labels'][0] == 'Иванов'
        assert data['datasets'][0]['data'][0] == 1

    def test_api_stage_duration(self, client, auth_client, database):
        """Тест: API для длительности этапов возвращает корректный JSON."""
        client = auth_client('manager', 'password123')
        
        # Добавляем тестовые данные в историю
        part = db.session.get(Part, 'TEST-001')
        part.date_added = datetime.datetime.utcnow() - datetime.timedelta(hours=2)
        db.session.add(StatusHistory(part_id='TEST-001', status='Резка', operator_name='Иванов', quantity=1, timestamp=datetime.datetime.utcnow() - datetime.timedelta(hours=1)))
        db.session.commit()
        
        response = client.get(url_for('admin.report.api_report_stage_duration'))
        assert response.status_code == 200
        assert response.is_json
        data = response.get_json()
        assert 'labels' in data
        assert 'datasets' in data
        assert data['labels'][0] == 'Резка'
        assert data['datasets'][0]['data'][0] > 0 # Время должно быть положительным