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

def list_rooms():
    rows = _all("""
        SELECT r.id_room, r.id_place, r.name, r.view, r.description, r.room_points,
               COUNT(p.id_pc_setup) AS pc_total,
               COALESCE(SUM(p.status = 'ready'), 0) AS pc_ready,
               (SELECT MIN(t.unit_price) FROM tariff t WHERE t.id_room = r.id_room) AS min_price
        FROM room r
        LEFT JOIN pc_setup p ON p.id_room = r.id_room
        GROUP BY r.id_room
        ORDER BY r.id_room
    """)
    for r in rows:
        r['room_points'] = _points(r['room_points'])
        r['pc_ready'] = int(r['pc_ready'])
    return rows
 
 
def get_room(room_id):
    row = _one(
        'SELECT id_room, id_place, name, view, description, room_points '
        'FROM room WHERE id_room = %s', [room_id]
    )
    if row:
        row['room_points'] = _points(row['room_points'])
    return row

def list_tariffs(room_id):
    return _all(
        'SELECT id_tariff, id_room, name, description, unit_price, duration_minutes '
        'FROM tariff WHERE id_room = %s ORDER BY duration_minutes, unit_price',
        [room_id],
    )

def room_pcs(room_id, start=None, end=None):
    """
    Места зоны. Если передан интервал [start, end) — у каждого места
    добавляется busy (занято на это время) и bookable.
    """
    busy_sql, params = '0', []
    if start and end:
        busy_sql = """EXISTS (
            SELECT 1 FROM reserve_pc_setup x
            JOIN reserve v ON v.id_reserve = x.id_reserve
            WHERE x.id_pc_setup = p.id_pc_setup
              AND v.status = 'active'
              AND x.start_time < %s AND x.end_time > %s)"""
        params = [end, start]
    rows = _all(f"""
        SELECT p.id_pc_setup, p.id_room, p.pc_setup_number, p.status,
               p.pos_x, p.pos_y, p.rotation,
               s.cpu, s.gpu, s.ram, s.monitor, s.mouse, s.keyboard, s.headphones, s.chair,
               {busy_sql} AS busy
        FROM pc_setup p
        JOIN pc_setup_spec s ON s.id_pc_setup_spec = p.id_pc_setup_spec
        WHERE p.id_room = %s
        ORDER BY p.pc_setup_number
    """, params + [room_id])
    for r in rows:
        r['busy'] = bool(r['busy'])
        r['bookable'] = r['status'] == PC_READY and not r['busy']
    return rows

def _check_window(start):
    now = timezone.now()
    if start < now - PAST_TOLERANCE:
        raise ServiceError('Нельзя забронировать время в прошлом.')
    days = settings.MAX_BOOKING_DAYS_AHEAD
    if start > now + timedelta(days=days):
        raise ServiceError(f'Нельзя бронировать более чем на {days} дн. вперёд.')
 
 
def _slot_busy(cur, pc_id, start, end, exclude_item=None):
    sql = """SELECT 1 FROM reserve_pc_setup x
             JOIN reserve v ON v.id_reserve = x.id_reserve
             WHERE x.id_pc_setup = %s AND v.status = 'active'
               AND x.start_time < %s AND x.end_time > %s"""
    params = [pc_id, end, start]
    if exclude_item is not None:
        sql += ' AND x.id_reserve_pc <> %s'
        params.append(exclude_item)
    cur.execute(sql + ' LIMIT 1', params)
    return cur.fetchone() is not None
 
 
def _recalc_price(cur, reserve_id):
    cur.execute("""
        UPDATE reserve SET final_price = (
            SELECT COALESCE(SUM(t.unit_price * x.tariff_unit_count), 0)
            FROM reserve_pc_setup x JOIN tariff t ON t.id_tariff = x.id_tariff
            WHERE x.id_reserve = %s)
        WHERE id_reserve = %s
    """, [reserve_id, reserve_id])
 
 
def create_booking(account_id, pc_id, tariff_id, units, start):
    """Создаёт бронь из одного места. Возвращает id_reserve."""
    units = _to_int(units, 'количество единиц')
    max_units = getattr(settings, 'MAX_BOOKING_UNITS', 24)
    if units < 1 or units > max_units:
        raise ServiceError(f'Количество единиц тарифа: от 1 до {max_units}.')
    if not isinstance(start, datetime):
        raise ServiceError('Укажите время начала.')
    _check_window(start)
 
    with transaction.atomic(), connection.cursor() as cur:
        # блокируем строку ПК: параллельные брони этого места встанут в очередь
        cur.execute(
            'SELECT id_room, status FROM pc_setup WHERE id_pc_setup = %s FOR UPDATE',
            [pc_id],
        )
        pc = cur.fetchone()
        if not pc:
            raise ServiceError('Место не найдено.')
        pc_room, pc_status = pc
        if pc_status != PC_READY:
            raise ServiceError('Это место сейчас недоступно.')
 
        cur.execute('SELECT is_active FROM account WHERE id_account = %s', [account_id])
        acc = cur.fetchone()
        if not acc or not acc[0]:
            raise ServiceError('Аккаунт заблокирован или не существует.')
 
        cur.execute(
            'SELECT id_room, unit_price, duration_minutes FROM tariff WHERE id_tariff = %s',
            [tariff_id],
        )
        tariff = cur.fetchone()
        if not tariff:
            raise ServiceError('Тариф не найден.')
        t_room, unit_price, duration = tariff
        if t_room != pc_room:
            raise ServiceError('Тариф относится к другой зоне.')
 
        end = start + timedelta(minutes=duration * units)
        if _slot_busy(cur, pc_id, start, end):
            raise ServiceError('Это место уже занято на выбранное время.')
 
        cur.execute(
            "INSERT INTO reserve (id_account, created_at, final_price, status) "
            "VALUES (%s, %s, %s, 'active')",
            [account_id, timezone.now(), unit_price * units],
        )
        reserve_id = cur.lastrowid
        cur.execute(
            'INSERT INTO reserve_pc_setup '
            '(id_reserve, id_pc_setup, id_tariff, tariff_unit_count, start_time, end_time) '
            'VALUES (%s, %s, %s, %s, %s, %s)',
            [reserve_id, pc_id, tariff_id, units, start, end],
        )
        return reserve_id
 
 
def list_reserves(account_id=None, only_active=False):
    """
    Брони с вложенными местами (ключ items).
    account_id=None -> все брони (для персонала).
    Для каждой брони считается can_client_cancel (правило «за N минут до начала»).
    """
    where, params = [], []
    if account_id is not None:
        where.append('v.id_account = %s')
        params.append(account_id)
    if only_active:
        where.append("v.status = 'active'")
    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''
 
    reserves = _all(f"""
        SELECT v.id_reserve, v.id_account, a.username, v.created_at,
               v.final_price, v.status,
               MIN(x.start_time) AS first_start, MAX(x.end_time) AS last_end
        FROM reserve v
        LEFT JOIN account a ON a.id_account = v.id_account
        LEFT JOIN reserve_pc_setup x ON x.id_reserve = v.id_reserve
        {where_sql}
        GROUP BY v.id_reserve, v.id_account, a.username, v.created_at, v.final_price, v.status
        ORDER BY first_start DESC, v.id_reserve DESC
    """, params)
    if not reserves:
        return []
 
    ids = [r['id_reserve'] for r in reserves]
    marks = ', '.join(['%s'] * len(ids))
    items = _all(f"""
        SELECT x.id_reserve_pc, x.id_reserve, x.id_pc_setup, p.pc_setup_number,
               rm.id_room, rm.name AS room_name,
               t.name AS tariff_name, t.unit_price, t.duration_minutes,
               x.tariff_unit_count, x.start_time, x.end_time
        FROM reserve_pc_setup x
        JOIN pc_setup p ON p.id_pc_setup = x.id_pc_setup
        JOIN room rm ON rm.id_room = p.id_room
        JOIN tariff t ON t.id_tariff = x.id_tariff
        WHERE x.id_reserve IN ({marks})
        ORDER BY x.start_time
    """, ids)
 
    by_reserve = {}
    for it in items:
        by_reserve.setdefault(it['id_reserve'], []).append(it)
 
    now = timezone.now()
    delta = timedelta(minutes=settings.CLIENT_CANCEL_BEFORE_MINUTES)
    for r in reserves:
        r['items'] = by_reserve.get(r['id_reserve'], [])
        first = r['first_start']
        r['can_client_cancel'] = (
            r['status'] == RESERVE_ACTIVE and (first is None or first - now >= delta)
        )
    return reserves
 
 
def cancel_reserve(reserve_id, user):
    """
    Клиент: только свою и не позже чем за CLIENT_CANCEL_BEFORE_MINUTES до начала.
    Админ / суперпользователь: любую активную.
    """
    reserve_id = _to_int(reserve_id, 'номер брони')
    with transaction.atomic(), connection.cursor() as cur:
        cur.execute(
            'SELECT id_account, status FROM reserve WHERE id_reserve = %s FOR UPDATE',
            [reserve_id],
        )
        row = cur.fetchone()
        if not row:
            raise ServiceError('Бронь не найдена.')
        owner, status = row
        if status != RESERVE_ACTIVE:
            raise ServiceError('Бронь уже отменена.')
        if not user.is_club_admin:
            if owner != user.id:
                raise ServiceError('Это чужая бронь.')
            cur.execute(
                'SELECT MIN(start_time) FROM reserve_pc_setup WHERE id_reserve = %s',
                [reserve_id],
            )
            first = cur.fetchone()[0]
            limit = settings.CLIENT_CANCEL_BEFORE_MINUTES
            if first is not None and first - timezone.now() < timedelta(minutes=limit):
                raise ServiceError(
                    f'Отменить можно не позже чем за {limit} мин. до начала. '
                    f'Обратитесь к администратору.'
                )
        cur.execute(
            "UPDATE reserve SET status = 'cancelled' WHERE id_reserve = %s", [reserve_id]
        )
 
 
def extend_booking_item(item_id, extra_units):
    """Админ: добавить время (единицы тарифа) к месту в брони."""
    item_id = _to_int(item_id, 'номер места в брони')
    extra = _to_int(extra_units, 'количество единиц')
    if extra < 1:
        raise ServiceError('Добавить можно минимум одну единицу тарифа.')
 
    with transaction.atomic(), connection.cursor() as cur:
        # одна блокирующая выборка: место в брони, тариф, бронь и сам ПК
        cur.execute("""
            SELECT x.id_reserve, x.id_pc_setup, x.tariff_unit_count, x.end_time,
                   t.duration_minutes, v.status
            FROM reserve_pc_setup x
            JOIN tariff t ON t.id_tariff = x.id_tariff
            JOIN reserve v ON v.id_reserve = x.id_reserve
            JOIN pc_setup p ON p.id_pc_setup = x.id_pc_setup
            WHERE x.id_reserve_pc = %s
            FOR UPDATE
        """, [item_id])
        row = cur.fetchone()
        if not row:
            raise ServiceError('Место в брони не найдено.')
        reserve_id, pc_id, count, end, duration, status = row
        if status != RESERVE_ACTIVE:
            raise ServiceError('Бронь отменена.')
        if end < timezone.now():
            raise ServiceError('Сеанс уже закончился.')
 
        new_end = end + timedelta(minutes=duration * extra)
        if _slot_busy(cur, pc_id, end, new_end, exclude_item=item_id):
            raise ServiceError('Дальше это место уже занято другой бронью.')
 
        cur.execute(
            'UPDATE reserve_pc_setup SET tariff_unit_count = %s, end_time = %s '
            'WHERE id_reserve_pc = %s',
            [count + extra, new_end, item_id],
        )
        _recalc_price(cur, reserve_id)
 
 
def _cancel_future_reserves(cur, account_id):
    """Отменяет ещё не начавшиеся брони аккаунта. Возвращает число."""
    cur.execute("""
        UPDATE reserve v SET v.status = 'cancelled'
        WHERE v.id_account = %s AND v.status = 'active'
          AND (SELECT MIN(x.start_time) FROM reserve_pc_setup x
               WHERE x.id_reserve = v.id_reserve) > %s
    """, [account_id, timezone.now()])
    return cur.rowcount