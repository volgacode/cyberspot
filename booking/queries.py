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

def register_account(username, password, role='client'):
    username = (username or '').strip()
    if not USERNAME_RE.fullmatch(username):
        raise ServiceError(
            'Логин: 3–150 символов — буквы, цифры и . @ + - _'
        )
    if role not in ROLE_LEVEL:
        raise ServiceError('Неизвестная роль.')
    if _one('SELECT 1 AS x FROM account WHERE username = %s', [username]):
        raise ServiceError('Этот логин уже занят.')
    try:
        with connection.cursor() as cur:
            cur.execute(
                'INSERT INTO account (username, password, role, is_active, date_joined) '
                'VALUES (%s, %s, %s, 1, %s)',
                [username, make_password(password), role, timezone.now()],
            )
            return cur.lastrowid
    except IntegrityError:
        raise ServiceError('Этот логин уже занят.')
 
def list_accounts():
    return _all(
        'SELECT id_account, username, role, is_active, date_joined, first_name, last_name '
        'FROM account ORDER BY id_account'
    )
 
def set_account_active(account_id, active, actor):
    """
    Блокировка / разблокировка. Заблокировать можно только пользователя
    с РОЛЬЮ НИЖЕ своей; при блокировке будущие брони отменяются.
    """
    account_id = _to_int(account_id, 'номер аккаунта')
    target = _one('SELECT id_account, role FROM account WHERE id_account = %s', [account_id])
    if not target:
        raise ServiceError('Аккаунт не найден.')
    if target['id_account'] == actor.id:
        raise ServiceError('Нельзя заблокировать самого себя.')
    if ROLE_LEVEL.get(target['role'], 0) >= actor.level:
        raise ServiceError('Недостаточно прав для этого аккаунта.')
    with transaction.atomic(), connection.cursor() as cur:
        cur.execute(
            'UPDATE account SET is_active = %s WHERE id_account = %s',
            [1 if active else 0, account_id],
        )
        if not active:
            return _cancel_future_reserves(cur, account_id)
    return 0
 
def set_account_role(account_id, role, actor):
    """Только суперпользователь; свою роль менять нельзя."""
    account_id = _to_int(account_id, 'номер аккаунта')
    if not actor.is_super:
        raise ServiceError('Недостаточно прав.')
    if role not in ROLE_LEVEL:
        raise ServiceError('Неизвестная роль.')
    if account_id == actor.id:
        raise ServiceError('Свою роль менять нельзя.')
    if not _exec('UPDATE account SET role = %s WHERE id_account = %s', [role, account_id]):
        if not _one('SELECT 1 AS x FROM account WHERE id_account = %s', [account_id]):
            raise ServiceError('Аккаунт не найден.')
 
def delete_own_account(user):
    """
    «Удаление» аккаунта клиентом — мягкое: история броней сохраняется,
    будущие брони отменяются, логин освобождается, войти нельзя.
    """
    with transaction.atomic(), connection.cursor() as cur:
        if user.is_super:
            cur.execute(
                "SELECT COUNT(*) FROM account WHERE role = 'superuser' AND is_active = 1"
            )
            if cur.fetchone()[0] <= 1:
                raise ServiceError('Нельзя удалить последнего суперпользователя.')
        _cancel_future_reserves(cur, user.id)
        cur.execute("""
            UPDATE account
            SET is_active = 0, username = CONCAT('deleted_', id_account),
                password = %s, first_name = NULL, last_name = NULL, avatar = NULL
            WHERE id_account = %s
        """, [make_password(None), user.id])

def set_place_points(place_id, points):
    points = _check_points(points, 'Контур помещения')
    _exec('UPDATE place SET place_points = %s WHERE id_place = %s',
          [json.dumps(points), place_id])
 
def set_room_points(room_id, points):
    points = _check_points(points, 'Контур комнаты')
    row = _one(
        'SELECT p.place_points FROM room r JOIN place p ON p.id_place = r.id_place '
        'WHERE r.id_room = %s', [room_id]
    )
    if row is None:
        raise ServiceError('Комната не найдена.')
    outline = _points(row['place_points'])
    if outline and points_are_valid(outline):
        if any(not point_in_polygon(x, y, outline) for x, y in points):
            raise ServiceError('Комната выходит за контур помещения.')
    _exec('UPDATE room SET room_points = %s WHERE id_room = %s',
          [json.dumps(points), room_id])
 
def move_pc(pc_id, x, y, rotation=0):
    """x = y = None — снять место с плана."""
    if x is None and y is None:
        _exec('UPDATE pc_setup SET pos_x = NULL, pos_y = NULL, rotation = NULL '
              'WHERE id_pc_setup = %s', [pc_id])
        return
    if x is None or y is None:
        raise ServiceError('Координаты X и Y задаются вместе.')
    x, y = _to_int(x, 'X'), _to_int(y, 'Y')
    rotation = 0 if rotation is None else _to_int(rotation, 'поворот')
    if x < 0 or y < 0:
        raise ServiceError('Координаты не могут быть отрицательными.')
    if not 0 <= rotation <= 359:
        raise ServiceError('Поворот: от 0 до 359°.')
    row = _one(
        'SELECT r.room_points FROM pc_setup p JOIN room r ON r.id_room = p.id_room '
        'WHERE p.id_pc_setup = %s', [pc_id]
    )
    if row is None:
        raise ServiceError('Место не найдено.')
    shape = _points(row['room_points'])
    if shape and points_are_valid(shape) and not point_in_polygon(x, y, shape):
        raise ServiceError('Центр ПК должен лежать внутри своей комнаты.')
    _exec('UPDATE pc_setup SET pos_x = %s, pos_y = %s, rotation = %s '
          'WHERE id_pc_setup = %s', [x, y, rotation, pc_id])
 
def set_pc_status(pc_id, status):
    if status not in (PC_READY, PC_NOT_READY):
        raise ServiceError('Неизвестный статус.')
    _exec('UPDATE pc_setup SET status = %s WHERE id_pc_setup = %s', [status, pc_id])
 
def create_room(place_id, name, description=None):
    name = (name or '').strip()
    if not name:
        raise ServiceError('Укажите название зоны.')
    if _one('SELECT 1 AS x FROM room WHERE id_place = %s AND name = %s', [place_id, name]):
        raise ServiceError('Зона с таким названием уже есть.')
    with connection.cursor() as cur:
        cur.execute(
            'INSERT INTO room (id_place, name, description) VALUES (%s, %s, %s)',
            [place_id, name, description or None],
        )
        return cur.lastrowid
 
def create_tariff(room_id, name, unit_price, duration_minutes, description=None):
    name = (name or '').strip()
    if not name:
        raise ServiceError('Укажите название тарифа.')
    try:
        price = float(unit_price)
    except (TypeError, ValueError):
        raise ServiceError('Некорректная цена.')
    duration = _to_int(duration_minutes, 'длительность')
    if price < 0:
        raise ServiceError('Цена не может быть отрицательной.')
    if duration < 1:
        raise ServiceError('Длительность должна быть больше нуля.')
    with connection.cursor() as cur:
        cur.execute(
            'INSERT INTO tariff (id_room, name, description, unit_price, duration_minutes) '
            'VALUES (%s, %s, %s, %s, %s)',
            [room_id, name, description or None, price, duration],
        )
        return cur.lastrowid
 
def list_specs():
    return _all('SELECT * FROM pc_setup_spec ORDER BY id_pc_setup_spec')
 
def create_spec(cpu, gpu, ram, monitor, mouse=None, keyboard=None, headphones=None, chair=None):
    with connection.cursor() as cur:
        cur.execute(
            'INSERT INTO pc_setup_spec (cpu, gpu, ram, monitor, mouse, keyboard, headphones, chair) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
            [cpu, gpu, ram, monitor, mouse, keyboard, headphones, chair],
        )
        return cur.lastrowid

def create_pc(room_id, spec_id, number, status=PC_READY):
    """Номер ПК сквозной в пределах помещения; проверяем под блокировкой помещения."""
    number = _to_int(number, 'номер ПК')
    if number < 1:
        raise ServiceError('Номер ПК должен быть больше нуля.')
    if status not in (PC_READY, PC_NOT_READY):
        raise ServiceError('Неизвестный статус.')
    with transaction.atomic(), connection.cursor() as cur:
        cur.execute(
            'SELECT r.id_place FROM room r WHERE r.id_room = %s', [room_id]
        )
        row = cur.fetchone()
        if not row:
            raise ServiceError('Зона не найдена.')
        cur.execute('SELECT id_place FROM place WHERE id_place = %s FOR UPDATE', [row[0]])
        cur.execute("""
            SELECT 1 FROM pc_setup p JOIN room r ON r.id_room = p.id_room
            WHERE r.id_place = %s AND p.pc_setup_number = %s LIMIT 1
        """, [row[0], number])
        if cur.fetchone():
            raise ServiceError(f'ПК с номером {number} уже есть в этом помещении.')
        cur.execute(
            'INSERT INTO pc_setup (id_pc_setup_spec, id_room, pc_setup_number, status) '
            'VALUES (%s, %s, %s, %s)',
            [spec_id, room_id, number, status],
        )
        return cur.lastrowid

def list_all_pcs():
    """Все места с комнатой — для редактора плана."""
    return _all("""
        SELECT p.id_pc_setup, p.id_room, p.id_pc_setup_spec, p.pc_setup_number,
               p.status, p.pos_x, p.pos_y, p.rotation
        FROM pc_setup p ORDER BY p.id_room, p.pc_setup_number
    """)