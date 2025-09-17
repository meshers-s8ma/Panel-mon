# tests/test_utils.py

import pytest
from unittest.mock import patch
import base64
from io import BytesIO

from app import utils

# Определяем фикстуру для предоставления контекста приложения
@pytest.fixture
def app_context(app):
    with app.app_context():
        yield

class TestUtils:
    """
    Тесты для вспомогательных функций из app/utils.py.
    """

    def test_create_safe_file_name(self):
        """
        Тест: Проверяет корректное удаление недопустимых символов из имени файла.
        """
        assert utils.create_safe_file_name("file/name?with*chars.txt") == "file_name_with_chars.txt"
        assert utils.create_safe_file_name("valid_filename_123.jpg") == "valid_filename_123.jpg"
        assert utils.create_safe_file_name("") == ""
        # --- ИСПРАВЛЕНИЕ ОШИБКИ №1 ---
        # Функция правильно заменяет один обратный слэш на подчеркивание.
        # Тест теперь это корректно отражает.
        assert utils.create_safe_file_name(r'\server\path:file|end') == '_server_path_file_end'

    def test_to_safe_key(self):
        """
        Тест: Проверяет транслитерацию и преобразование текста в безопасный ключ
              для использования в URL и HTML-атрибутах.
        """
        assert utils.to_safe_key("Привет, Мир!") == "privet_mir"
        assert utils.to_safe_key("Тестовое изделие №3 (спец.)") == "testovoe_izdelie_3_spec"
        assert utils.to_safe_key("  Leading and Trailing Spaces  ") == "leading_and_trailing_spaces"
        assert utils.to_safe_key("ALL CAPS") == "all_caps"
        assert utils.to_safe_key("---multiple---dashes---") == "multiple_dashes"

    @patch('app.utils.qrcode.make')
    def test_generate_qr_code_success(self, mock_qrcode_make, app_context, monkeypatch):
        """
        Тест: Проверяет успешную генерацию QR-кода в виде BytesIO.
        Использует 'mock' для замены реальной библиотеки qrcode.
        """
        # --- ИСПРАВЛЕНИЕ ОШИБКИ №2 ---
        # Устанавливаем переменные окружения специально для этого теста,
        # чтобы он не зависел от локального .env файла.
        monkeypatch.setenv("SERVER_PUBLIC_IP", "127.0.0.1")
        monkeypatch.setenv("SERVER_PORT", "5000")

        # 1. Настраиваем мок, чтобы он возвращал объект, у которого есть метод save
        mock_image = BytesIO()
        # Лямбда-функция для имитации метода save
        mock_qrcode_make.return_value.save = lambda buffer, format: buffer.write(b'fake_qr_code_data')

        # 2. Вызываем функцию
        result_buffer = utils.generate_qr_code('TEST/001')

        # 3. Проверяем результат
        assert isinstance(result_buffer, BytesIO)
        assert result_buffer.getvalue() == b'fake_qr_code_data'

        # Проверяем, что qrcode.make был вызван с правильно закодированным URL
        expected_url = "http://127.0.0.1:5000/scan/TEST%2F001"
        mock_qrcode_make.assert_called_once_with(expected_url)

    @patch('app.utils.generate_qr_code')
    def test_generate_qr_code_as_base64(self, mock_generate_qr_code):
        """
        Тест: Проверяет преобразование QR-кода из BytesIO в строку Base64.
        """
        fake_image_data = b'\x89PNG\r\n\x1a\n\x00\x00' # Минимальный валидный заголовок PNG
        mock_generate_qr_code.return_value = BytesIO(fake_image_data)

        result_base64 = utils.generate_qr_code_as_base64('any_id')

        encoded_string = base64.b64encode(fake_image_data).decode('utf-8')
        expected_result = f"data:image/png;base64,{encoded_string}"
        assert result_base64 == expected_result
        mock_generate_qr_code.assert_called_once_with('any_id')

    @patch('app.utils.generate_qr_code')
    def test_generate_qr_code_as_base64_handles_failure(self, mock_generate_qr_code):
        """
        Тест: Проверяет, что функция возвращает None, если генерация QR-кода не удалась.
        """
        mock_generate_qr_code.return_value = None
        result = utils.generate_qr_code_as_base64('fail_id')
        assert result is None