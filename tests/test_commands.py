# tests/test_commands.py

import pytest
from click.testing import CliRunner
from app.commands import seed_command, seed_cypress_command
from app.models.models import db, User, Role, Part, Stage, RouteTemplate

@pytest.fixture(scope='module')
def runner():
    """Фикстура для запуска CLI команд."""
    return CliRunner()

class TestSeedCommand:
    """Тесты для команды `flask seed`."""

    # --- ИЗМЕНЕНИЕ: Используем фикстуру `db` вместо `database` ---
    def test_seed_creates_admin_and_roles_in_empty_db(self, runner, app, db):
        """Тест: `seed` создает роли и админа в пустой базе."""
        assert User.query.count() == 0
        assert Role.query.count() == 0
        
        result = runner.invoke(app.cli.get_command(None, 'seed'))
        
        assert result.exit_code == 0
        assert 'Роли успешно созданы.' in result.output
        assert 'Администратор успешно создан.' in result.output
        
        assert User.query.count() == 1
        assert Role.query.count() == 3
        
        admin = User.query.filter_by(username='admin').first()
        assert admin is not None
        assert admin.check_password('password123')

    # --- ИЗМЕНЕНИЕ: Используем фикстуру `db` и создаем пользователя вручную ---
    def test_seed_does_not_create_admin_if_users_exist(self, runner, app, db):
        """Тест: `seed` не создает админа, если пользователи уже есть."""
        # Вручную создаем пользователя, чтобы симулировать непустую БД
        Role.insert_roles()
        admin_role = Role.query.first()
        existing_user = User(username='existing', role=admin_role)
        db.session.add(existing_user)
        db.session.commit()
        
        initial_user_count = User.query.count()
        assert initial_user_count == 1
        
        result = runner.invoke(app.cli.get_command(None, 'seed'))
        
        assert result.exit_code == 0
        assert 'Пользователи уже существуют. Пропуск создания администратора.' in result.output
        assert User.query.count() == initial_user_count
            
    def test_seed_creates_random_password_in_production(self, runner, app, db):
        """Тест: `seed` создает случайный пароль в production-режиме."""
        app.config['ENV'] = 'production'
        
        result = runner.invoke(app.cli.get_command(None, 'seed'))
        
        assert result.exit_code == 0
        admin = User.query.filter_by(username='admin').first()
        assert admin is not None
        assert not admin.check_password('password123')
        assert 'Пароль:' in result.output
        
        app.config['ENV'] = 'testing'

class TestSeedCypressCommand:
    """Тесты для команды `flask seed-cypress`."""

    # --- ИЗМЕНЕНИЕ: Используем фикстуру `db` вместо `database` ---
    def test_seed_cypress_cleans_and_populates_db(self, runner, app, db):
        """Тест: `seed-cypress` полностью очищает и заполняет базу."""
        # Создаем "грязные" данные, которые должны быть удалены
        old_role = Role(name='Old Role')
        db.session.add(old_role)
        db.session.commit() # Commit, чтобы объект точно попал в БД
        old_user = User(username='old_user', role=old_role)
        old_part = Part(part_id='OLD-PART', product_designation='Old', name='Old', material='-')
        db.session.add_all([old_user, old_part])
        db.session.commit()

        assert User.query.filter_by(username='old_user').first() is not None
        assert Part.query.filter_by(part_id='OLD-PART').first() is not None
        
        # Запускаем команду
        result = runner.invoke(app.cli.get_command(None, 'seed-cypress'))
        
        assert result.exit_code == 0
        assert 'База данных готова для Cypress-тестов.' in result.output
        
        # Проверяем, что старых данных не осталось
        assert User.query.filter_by(username='old_user').first() is None
        assert Role.query.filter_by(name='Old Role').first() is None
        assert db.session.get(Part, 'OLD-PART') is None
        
        # Проверяем, что новые данные были созданы
        assert User.query.filter_by(username='admin').first() is not None
        assert db.session.get(Part, 'CY-TEST-001') is not None
        assert Stage.query.filter_by(name='Резка').first() is not None
        assert RouteTemplate.query.filter_by(is_default=True).first() is not None