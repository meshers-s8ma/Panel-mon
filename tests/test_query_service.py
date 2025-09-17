# tests/test_query_service.py

import pytest
from datetime import datetime, timedelta

from app import db
from app.services import query_service
from app.models.models import (
    Part, StatusHistory, AuditLog, PartNote, User, Stage, ResponsibleHistory
)

def test_get_combined_history(database):
    """
    Тест: Проверяет, что сервис `get_combined_history` корректно собирает,
    объединяет и сортирует все типы исторических событий для одной детали.
    """
    # 1. Получаем из фикстуры `database` необходимые объекты
    part = db.session.get(Part, 'TEST-001')
    admin = User.query.filter_by(username='admin').first()
    operator = User.query.filter_by(username='operator').first()
    stage = Stage.query.filter_by(name='Резка').first()
    
    # Убеждаемся, что все объекты найдены
    assert all([part, admin, operator, stage])

    # 2. Создаем разнообразные исторические события в разном порядке
    #    для проверки корректности финальной сортировки по времени.
    now = datetime.utcnow()
    
    # Событие 1: Статус (самое старое)
    status_event = StatusHistory(
        part_id=part.part_id,
        status=stage.name,
        operator_name='Тестер',
        quantity=1,
        timestamp=now - timedelta(days=2)
    )
    
    # Событие 2: Примечание
    note_event = PartNote(
        part_id=part.part_id,
        user_id=admin.id,
        stage_id=stage.id,
        text="Это тестовое примечание.",
        timestamp=now - timedelta(days=1)
    )
    
    # Событие 3: Запись в аудите
    audit_event = AuditLog(
        part_id=part.part_id,
        user_id=admin.id,
        action="Редактирование",
        details="Тестовое изменение.",
        category='part',
        timestamp=now - timedelta(hours=5)
    )

    # Событие 4: Смена ответственного (самое новое)
    responsible_event = ResponsibleHistory(
        part_id=part.part_id,
        user_id=operator.id,
        timestamp=now
    )
    
    db.session.add_all([status_event, note_event, audit_event, responsible_event])
    db.session.commit()

    # 3. Вызываем тестируемый сервис
    combined_history = query_service.get_combined_history(part)
    
    # 4. Проверяем результаты
    
    # а) Проверяем количество: должно быть 4 события
    assert len(combined_history) == 4
    
    # б) Проверяем порядок: события должны быть отсортированы от нового к старому
    assert combined_history[0]['type'] == 'responsible'
    assert combined_history[1]['type'] == 'audit'
    assert combined_history[2]['type'] == 'note'
    assert combined_history[3]['type'] == 'status'
    
    # в) Проверяем содержимое каждого типа события
    
    # Проверяем событие смены ответственного
    resp_entry = combined_history[0]
    assert resp_entry['action'] == "Назначен ответственный"
    assert resp_entry['user'].username == 'operator'
    
    # Проверяем событие аудита
    audit_entry = combined_history[1]
    assert audit_entry['action'] == "Редактирование"
    assert audit_entry['details'] == "Тестовое изменение."
    assert audit_entry['user'].username == 'admin'
    
    # Проверяем событие примечания
    note_entry = combined_history[2]
    assert note_entry['text'] == "Это тестовое примечание."
    assert note_entry['stage'].name == 'Резка'
    assert note_entry['author'].username == 'admin'
    
    # Проверяем событие статуса
    status_entry = combined_history[3]
    assert status_entry['status'] == 'Резка'
    assert status_entry['operator_name'] == 'Тестер'
    assert status_entry['quantity'] == 1