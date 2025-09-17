# wsgi.py

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from pythonjsonlogger import jsonlogger  # Новая зависимость для JSON-логов

from app import create_app
from config import config_by_name

# Загружаем переменные окружения из файла .env
load_dotenv()

# Определяем конфигурацию (development, production) на основе переменной окружения
config_name = os.environ.get('FLASK_ENV', 'development')
try:
    config_class = config_by_name[config_name]
except KeyError:
    sys.exit(f"Ошибка: Неверное имя конфигурации '{config_name}'. Допустимые значения: development, production, testing.")

# Создаем экземпляры приложения и SocketIO с помощью фабрики
app, socketio = create_app(config_class)

# --- Настройка логирования ---
# Логирование в файлы настраивается только тогда, когда приложение
# запущено не в режиме отладки (т.е., в production).
if not app.debug:
    # Убеждаемся, что папка для логов существует
    log_dir = os.path.join(app.instance_path, 'logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_file_path = os.path.join(log_dir, 'app.log')

    # Используем RotatingFileHandler, чтобы файлы логов не росли бесконечно
    file_handler = RotatingFileHandler(
        log_file_path, maxBytes=10485760, backupCount=5, encoding='utf-8'
    )
    
    # --- УЛУЧШЕНИЕ: Используем JSON-форматтер ---
    # Определяем формат JSON-сообщения. Включаем стандартные поля,
    # а также путь к файлу и номер строки, где произошло событие.
    log_format = '%(asctime)s %(name)s %(levelname)s %(pathname)s %(lineno)d %(message)s'
    formatter = jsonlogger.JsonFormatter(log_format)
    file_handler.setFormatter(formatter)
    
    # Добавляем наш настроенный обработчик к логгеру Flask
    app.logger.addHandler(file_handler)
    
    # Устанавливаем уровень логирования из переменных окружения (по умолчанию INFO)
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    app.logger.setLevel(log_level)
    
    # Записываем первое сообщение в лог о старте приложения
    app.logger.info('Product Tracker application startup')