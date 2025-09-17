# app/admin/__init__.py

from flask import Blueprint

# 1. Создаем главный "сборный" блюпринт для всей админки.
# Он будет зарегистрирован в главном файле app/__init__.py.
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# 2. Импортируем дочерние блюпринты ЗДЕСЬ, а не в глобальной области видимости
#    основного файла приложения. Это предотвращает циклические импорты.
from .routes import management_routes, part_routes, report_routes, user_routes

# 3. Регистрируем каждый дочерний блюпринт внутри нашего главного "сборного" блюпринта.
#    Это делает их конечные точки доступными через префикс 'admin.'.
#    Например, эндпоинт 'login' из 'user_bp' станет доступен как 'admin.user.login'.
#    URL-префиксы, заданные здесь, добавляются к префиксу главного блюпринта.
#    Например, URL для 'part_bp' будет /admin/part/...
admin_bp.register_blueprint(management_routes.management_bp)
admin_bp.register_blueprint(part_routes.part_bp, url_prefix='/part')
admin_bp.register_blueprint(report_routes.report_bp, url_prefix='/report')
admin_bp.register_blueprint(user_routes.user_bp, url_prefix='/user')