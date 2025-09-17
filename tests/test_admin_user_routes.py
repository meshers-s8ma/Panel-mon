# tests/test_admin_user_routes.py

from flask import url_for
from app import db
from app.models.models import User, Role, Permission

class TestUserAndRoleManagement:
    """Тесты для управления пользователями и ролями."""

    def test_create_user(self, client, auth_client, database):
        """Тест: Администратор может создать пользователя."""
        client = auth_client('admin', 'password123')
        role = Role.query.filter_by(name='Operator').first()
        assert role is not None
        
        client.post(url_for('admin.user.add_user'), data={'username': 'user1', 'password': 'password', 'role': role.id})
        user = User.query.filter_by(username='user1').first()
        assert user is not None

    def test_edit_user(self, client, auth_client, database):
        """Тест: Администратор может редактировать пользователя."""
        client = auth_client('admin', 'password123')
        user = User.query.filter_by(username='manager').first()
        role = Role.query.filter_by(name='Operator').first()
        assert user is not None
        assert role is not None
        
        client.post(url_for('admin.user.edit_user', user_id=user.id), data={'username': 'user2', 'role': role.id})
        db.session.refresh(user)
        assert user.username == 'user2'

    def test_delete_user(self, client, auth_client, database):
        """Тест: Администратор может удалить другого пользователя."""
        client = auth_client('admin', 'password123')
        user = User.query.filter_by(username='manager').first()
        assert user is not None
        
        client.post(url_for('admin.user.delete_user', user_id=user.id))
        assert db.session.get(User, user.id) is None

    # --- НАЧАЛО ИСПРАВЛЕНИЯ: Полностью переписанный тест ---
    def test_cannot_delete_last_admin(self, client, auth_client, database):
        """Тест: Нельзя удалить последнего администратора в системе."""
        # 1. Находим и удаляем всех пользователей, КРОМЕ админа
        admin_user = User.query.filter_by(username='admin').first()
        non_admins = User.query.filter(User.id != admin_user.id).all()
        for user in non_admins:
            db.session.delete(user)
        
        # 2. Создаем ВТОРОГО администратора, чтобы было кого удалять
        admin_role = Role.query.filter_by(name='Administrator').first()
        admin2 = User(username='admin2', role=admin_role)
        admin2.set_password('password123')
        db.session.add(admin2)
        db.session.commit()
        
        # 3. Логинимся под первым админом
        client = auth_client('admin', 'password123')
        
        # 4. Пытаемся удалить второго (не последнего) админа - это должно сработать
        response_delete_admin2 = client.post(url_for('admin.user.delete_user', user_id=admin2.id))
        assert db.session.get(User, admin2.id) is None
        
        # 5. Убеждаемся, что в системе остался только один пользователь - admin
        assert User.query.count() == 1
        
        # 6. Пытаемся удалить ПОСЛЕДНЕГО оставшегося админа
        response = client.post(url_for('admin.user.delete_user', user_id=admin_user.id), follow_redirects=True)
        
        # 7. Проверяем, что получили правильное сообщение об ошибке
        assert response.status_code == 200
        # Проверяем, что сработала именно проверка на ПОСЛЕДНЕГО АДМИНА
        assert 'Нельзя удалить последнего администратора в системе.' in response.data.decode('utf-8')
        # Убеждаемся, что админ НЕ удален
        assert db.session.get(User, admin_user.id) is not None
    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

    def test_role_crud_and_errors(self, client, auth_client, database):
        """Тест: Полный CRUD-цикл для ролей и обработка ошибок."""
        client = auth_client('admin', 'password123')
        
        client.post(url_for('admin.user.add_role'), data={'name': 'Role1', 'permissions': [Permission.ADD_PARTS]})
        role = Role.query.filter_by(name='Role1').first()
        assert role is not None
        
        client.post(url_for('admin.user.edit_role', role_id=role.id), data={'name': 'Role2', 'permissions': []})
        db.session.refresh(role)
        assert role.name == 'Role2'
        
        user = User.query.filter_by(username='manager').first()
        response_del_fail = client.post(url_for('admin.user.delete_role', role_id=user.role.id), follow_redirects=True)
        assert 'которая присвоена пользователям' in response_del_fail.data.decode('utf-8')
        
        client.post(url_for('admin.user.delete_role', role_id=role.id))
        assert db.session.get(Role, role.id) is None

    def test_audit_log_pages_load(self, client, auth_client, database):
        """Тест: Страницы с логами загружаются успешно."""
        client = auth_client('admin', 'password123')
        assert client.get(url_for('admin.user.audit_log')).status_code == 200
        assert client.get(url_for('admin.user.user_log')).status_code == 200