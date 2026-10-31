"""
Слой данных на чистом SQL (MySQL). Здесь же живут все бизнес-правила,
потому что в схеме нет триггеров и CHECK-ограничений.
Время везде наивное (USE_TZ = False): Python и MySQL работают с одним
локальным временем клуба.
"""
import json
import re
from datetime import datetime, timedelta
 
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone
 
from .geometry import point_in_polygon, points_are_valid, validate_points
from .models import ROLE_LEVEL

PC_READY = 'ready'
PC_NOT_READY = 'not ready'
RESERVE_ACTIVE = 'active'
RESERVE_CANCELLED = 'cancelled'
 
PAST_TOLERANCE = timedelta(minutes=5) # допуск «начало в прошлом»
USERNAME_RE = re.compile(r'[\w.@+-]{3,150}')

class ServiceError(Exception):
    """Нарушено бизнес-правило. Текст можно показывать пользователю."""

def _rows(cur):
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
 
 
def _all(sql, params=()):
    with connection.cursor() as cur:
        cur.execute(sql, params)
        return _rows(cur)
 
 
def _one(sql, params=()):
    rows = _all(sql, params)
    return rows[0] if rows else None
 
 
def _exec(sql, params=()):
    with connection.cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount
 
 
def _points(value):
    """JSON-колонка приходит из драйвера строкой."""
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        value = value.decode()
    if isinstance(value, str):
        return json.loads(value)
    return value
 
 
def _check_points(points, what):
    try:
        validate_points(points)
    except ValidationError as e:
        raise ServiceError(f'{what}: ' + ' '.join(e.messages))
    return [[int(x), int(y)] for x, y in points]
 
 
def _to_int(value, what='значение'):
    try:
        if isinstance(value, bool):
            raise ValueError
        return int(value)
    except (TypeError, ValueError):
        raise ServiceError(f'Некорректное {what}.')

def get_place():
    """Клуб единственный: берём первое помещение."""
    row = _one(
        'SELECT id_place, name, view, description, place_points '
        'FROM place ORDER BY id_place LIMIT 1'
    )
    if row:
        row['place_points'] = _points(row['place_points'])
    return row