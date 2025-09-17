# tests/test_admin_management_routes.py

from flask import url_for
from app import db
from app.models.models import Part, Stage, RouteTemplate

class TestAdminManagementRoutes:
    """Тесты для маршрутов управления (этапы, маршруты)."""

    def test_stage_crud_and_errors(self, client, auth_client, database):
        """Тест: Полный цикл CRUD для этапов и обработка ошибок."""
        client = auth_client('admin', 'password123')
        
        # Create
        client.post(url_for('admin.management.add_stage'), data={'name': 'New Stage'})
        stage = Stage.query.filter_by(name='New Stage').first()
        assert stage is not None
        
        # Create Duplicate Fails
        response_fail = client.post(url_for('admin.management.add_stage'), data={'name': 'New Stage'}, follow_redirects=True)
        assert 'уже существует'.encode('utf-8') in response_fail.data
        
        # Delete Used Fails
        part = db.session.get(Part, 'TEST-001')
        stage_in_use = part.route_template.stages[0].stage
        response_del_fail = client.post(url_for('admin.management.delete_stage', stage_id=stage_in_use.id), follow_redirects=True)
        assert 'Нельзя удалить этап'.encode('utf-8') in response_del_fail.data
        
        # Delete
        client.post(url_for('admin.management.delete_stage', stage_id=stage.id))
        assert db.session.get(Stage, stage.id) is None

    def test_route_crud_and_errors(self, client, auth_client, database):
        """Тест: Полный цикл CRUD для маршрутов и обработка ошибок."""
        client = auth_client('admin', 'password123')
        stage1 = Stage.query.filter_by(name='Test Stage 1').first()
        stage2 = Stage.query.filter_by(name='Test Stage 2').first()
        
        # Проверяем, что этапы существуют, прежде чем их использовать
        assert stage1 is not None
        assert stage2 is not None
        
        # Create
        client.post(url_for('admin.management.add_route'), data={'name': 'Route1', 'stages': [stage1.id]})
        route = RouteTemplate.query.filter_by(name='Route1').first()
        assert route is not None
        
        # Edit
        client.post(url_for('admin.management.edit_route', route_id=route.id), data={'name': 'Route2', 'stages': [stage1.id, stage2.id]})
        db.session.refresh(route)
        assert route.name == 'Route2'
        
        # Delete Used Fails
        part = db.session.get(Part, 'TEST-001')
        part.route_template_id = route.id
        db.session.commit()
        response_del_fail = client.post(url_for('admin.management.delete_route', route_id=route.id), follow_redirects=True)
        assert 'Нельзя удалить маршрут'.encode('utf-8') in response_del_fail.data
        
        # Delete
        part.route_template_id = RouteTemplate.query.filter(RouteTemplate.id != route.id).first().id
        db.session.commit()
        client.post(url_for('admin.management.delete_route', route_id=route.id))
        assert db.session.get(RouteTemplate, route.id) is None