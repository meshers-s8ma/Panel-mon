# tests/test_models.py

from app import db
from app.models.models import Role, Permission, User

def test_role_permission_management(database):
    """Тест: Проверяет добавление, проверку и удаление прав у роли."""
    # Создаем новую роль
    new_role = Role(name='Test Role', permissions=0)
    db.session.add(new_role)
    db.session.commit()
    
    # 1. Проверяем, что изначально прав нет
    assert not new_role.has_permission(Permission.ADD_PARTS)
    
    # 2. Добавляем право
    new_role.add_permission(Permission.ADD_PARTS)
    db.session.commit()
    assert new_role.has_permission(Permission.ADD_PARTS)
    
    # 3. Добавляем еще одно право
    new_role.add_permission(Permission.VIEW_REPORTS)
    db.session.commit()
    assert new_role.has_permission(Permission.ADD_PARTS)
    assert new_role.has_permission(Permission.VIEW_REPORTS)
    
    # 4. Удаляем первое право
    new_role.remove_permission(Permission.ADD_PARTS)
    db.session.commit()
    assert not new_role.has_permission(Permission.ADD_PARTS)
    assert new_role.has_permission(Permission.VIEW_REPORTS)
    
    # 5. Сбрасываем все права
    new_role.reset_permissions()
    db.session.commit()
    assert not new_role.has_permission(Permission.VIEW_REPORTS)

def test_user_password_hashing(database):
    """Тест: Проверяет корректность установки и проверки пароля."""
    user = User.query.filter_by(username='operator').first()
    
    assert user.password_hash is not None
    assert user.check_password('password123')
    assert not user.check_password('wrongpassword')
    
    user.set_password('newpass')
    db.session.commit()

    # Получаем пользователя заново, чтобы убедиться, что хэш сохранился
    user_updated = User.query.filter_by(username='operator').first()
    assert user_updated.check_password('newpass')
    assert not user_updated.check_password('password123')

def test_user_permission_checks(database):
    """Тест: Проверяет, что методы can() и is_admin() работают корректно."""
    admin = User.query.filter_by(username='admin').first()
    manager = User.query.filter_by(username='manager').first()
    operator = User.query.filter_by(username='operator').first()

    # Проверки для админа
    assert admin.is_admin()
    assert admin.can(Permission.MANAGE_USERS)
    assert admin.can(Permission.ADD_PARTS)

    # Проверки для менеджера
    assert not manager.is_admin()
    assert not manager.can(Permission.MANAGE_USERS)
    assert manager.can(Permission.ADD_PARTS)
    assert manager.can(Permission.VIEW_REPORTS)

    # Проверки для оператора
    assert not operator.is_admin()
    assert not operator.can(Permission.ADD_PARTS)
    assert operator.can(Permission.GENERATE_QR)

def test_user_default_role(database):
    """Тест: Проверяет, что новому пользователю присваивается роль по умолчанию."""
    # Создаем пользователя без явного указания роли
    new_user = User(username='new_default_user')
    new_user.set_password('password')
    db.session.add(new_user)
    db.session.commit()
    
    # Роль по умолчанию - 'Operator'
    default_role = Role.query.filter_by(default=True).first()
    assert default_role is not None
    assert new_user.role is not None
    assert new_user.role.name == 'Operator'
    assert new_user.role_id == default_role.id
    
    # Проверяем, что права соответствуют роли по умолчанию
    assert new_user.can(Permission.GENERATE_QR)
    assert not new_user.can(Permission.ADD_PARTS)