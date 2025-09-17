# tests/test_auth.py

import pytest
from flask import url_for

class TestAccessAndAuth:
    def test_dashboard_access_for_guest(self, client, database):
        response = client.get(url_for('main.dashboard'))
        assert response.status_code == 200
        assert 'Панель мониторинга'.encode('utf-8') in response.data

    def test_admin_pages_require_login(self, client, database):
        response = client.get(url_for('admin.user.list_users'), follow_redirects=True)
        assert response.status_code == 200
        assert 'Вход в систему'.encode('utf-8') in response.data

    def test_login_and_logout(self, client, database):
        # --- ВХОД ---
        response_login = client.post(url_for('admin.user.login'), data={
            'username': 'admin', 'password': 'password123'
        })
        assert response_login.status_code == 302
        
        # Проверяем flash-сообщение о входе
        with client.session_transaction() as session:
            assert 'успешно вошли' in session['_flashes'][0][1]

        # --- ВЫХОД ---
        # --- ИСПРАВЛЕНИЕ: Делаем запрос на выход ---
        response_logout = client.get(url_for('admin.user.logout'))
        assert response_logout.status_code == 302
        
        # --- ИСПРАВЛЕНИЕ: Теперь проверяем сессию ПОСЛЕ запроса на выход ---
        # Мы должны "поймать" сессию, которая была установлена редиректом.
        # Для этого мы делаем еще один запрос (на страницу редиректа)
        # и проверяем flash-сообщение уже на этой странице.
        response_after_logout = client.get(response_logout.location, follow_redirects=True)
        assert 'Вы вышли из системы'.encode('utf-8') in response_after_logout.data