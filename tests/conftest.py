# tests/conftest.py

import pytest
import sys
import os
from flask import url_for
from flask_login import login_user

# Добавляем корневую папку проекта в путь Python
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db as _db
from config import TestingConfig
from app.models.models import User, Stage, RouteTemplate, RouteStage, Part, Role

@pytest.fixture(scope='session')
def app():
    """Создает экземпляр приложения для всей сессии тестов."""
    flask_app, _ = create_app(TestingConfig)
    flask_app.config['WTF_CSRF_ENABLED'] = False
    return flask_app

@pytest.fixture(scope='function')
def db(app):
    """Создает и очищает базу данных для каждого теста."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.remove()
        _db.drop_all()

@pytest.fixture(scope='function')
def database(db):
    """Наполняет базу данных минимально необходимыми данными для каждого теста."""
    Role.insert_roles()
    admin_role = Role.query.filter_by(name='Administrator').first()
    manager_role = Role.query.filter_by(name='Manager').first()
    operator_role = Role.query.filter_by(name='Operator').first()
    
    admin = User(username='admin', role=admin_role)
    admin.set_password('password123')
    manager = User(username='manager', role=manager_role)
    manager.set_password('password123')
    operator = User(username='operator', role=operator_role)
    operator.set_password('password123')
    
    stage1 = Stage(name='Резка')
    stage2 = Stage(name='Сверловка')
    test_stage1 = Stage(name='Test Stage 1')
    test_stage2 = Stage(name='Test Stage 2')
    route1 = RouteTemplate(name='Стандартный маршрут', is_default=True)
    
    db.session.add_all([admin, manager, operator, stage1, stage2, test_stage1, test_stage2, route1])
    db.session.commit()

    rs1 = RouteStage(template_id=route1.id, stage_id=stage1.id, order=0)
    rs2 = RouteStage(template_id=route1.id, stage_id=stage2.id, order=1)
    
    part1 = Part(part_id='TEST-001', product_designation='Тестовое изделие', name='Крышка', material='Ст3', route_template_id=route1.id)
    
    db.session.add_all([rs1, rs2, part1])
    db.session.commit()
    return db

@pytest.fixture(scope='function')
def client(app):
    """Предоставляет тестовый клиент."""
    return app.test_client()

@pytest.fixture(scope='function')
def auth_client(client, app):
    """
    Фикстура для аутентификации через POST-запрос.
    Может оставлять flash-сообщения о входе в сессии.
    """
    def login(username, password):
        with app.test_request_context():
            client.post(url_for('admin.user.login'), data={'username': username, 'password': password})
        return client
    return login

@pytest.fixture(scope='function')
def clean_auth_client(client, app):
    """
    Фикстура для "чистой" аутентификации без выполнения POST-запроса на login.
    Она не создает flash-сообщений о входе, что полезно для тестов,
    проверяющих конкретные flash-сообщения от других действий.
    """
    def login(username):
        with app.test_request_context():
            user = User.query.filter_by(username=username).first()
            login_user(user)
        return client
    return login