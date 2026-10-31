import json
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import redire
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.decorators.http import require_POST
 
from . import queries
from .decorators import role_required
from .queries import ServiceError
 
DT_FORMAT = '%Y-%m-%dT%H:%M'   # формат <input type="datetime-local">

def _parse_dt(value):
    try:
        return datetime.strptime(value, DT_FORMAT)
    except (TypeError, ValueError):
        return None
 
def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
 
def _safe_next(request, fallback):
    nxt = request.POST.get('next') or request.GET.get('next')
    if nxt and url_has_allowed_host_and_scheme(nxt, request.get_host()):
        return nxt
    return reverse(fallback)
 
def _json_body(request):
    try:
        data = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        raise ServiceError('Некорректный JSON.')
    if not isinstance(data, dict):
        raise ServiceError('Ожидался JSON-объект.')
    return data

def home(request):
    return redirect('zones' if request.user.is_authenticated else 'login')
 
def register_view(request):
    if request.user.is_authenticated:
        return redirect('zones')
    error, username = None, ''
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        try:
            validate_password(password)
            queries.register_account(username, password)
        except ValidationError as e:
            error = ' '.join(e.messages)
        except ServiceError as e:
            error = str(e)
        else:
            user = authenticate(request, username=username, password=password)
            login(request, user)
            return redirect('zones')
    return render(request, 'booking/register.html', {'error': error, 'username': username})
 
def login_view(request):
    if request.user.is_authenticated:
        return redirect('zones')
    error, username = None, ''
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        user = authenticate(
            request, username=username, password=request.POST.get('password', '')
        )
        if user is None:
            error = 'Неверный логин или пароль, либо аккаунт заблокирован.'
        else:
            login(request, user)
            return redirect(_safe_next(request, 'zones'))
    return render(request, 'booking/login.html', {
        'error': error, 'username': username, 'next': request.GET.get('next', ''),
    })
 
@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')
 
@require_POST
@role_required('client')
def delete_account(request):
    try:
        queries.delete_own_account(request.user)
    except ServiceError as e:
        messages.error(request, str(e))
        return redirect('my_reserves')
    logout(request)
    return redirect('login')

@role_required('client')
def zones(request):
    return render(request, 'booking/zones.html', {
        'place': queries.get_place(),
        'rooms': queries.list_rooms(),
    })
 
@role_required('client')
def zone_detail(request, room_id):
    room = queries.get_room(room_id)
    if room is None:
        raise Http404
    tariffs = queries.list_tariffs(room_id)
 
    tariff_id = _int(request.GET.get('tariff'), None)
    tariff = next((t for t in tariffs if t['id_tariff'] == tariff_id), None) \
        or (tariffs[0] if tariffs else None)
    units = max(1, _int(request.GET.get('units'), 1))
    start = _parse_dt(request.GET.get('start'))
 
    end = None
    if tariff and start:
        end = start + timedelta(minutes=tariff['duration_minutes'] * units)
 
    now = timezone.now()
    return render(request, 'booking/zone_detail.html', {
        'place': queries.get_place(),
        'room': room,
        'tariffs': tariffs,
        'tariff': tariff,
        'units': units,
        'start': start,
        'end': end,
        'pcs': queries.room_pcs(room_id, start, end),
        'min_start': now.strftime(DT_FORMAT),
        'max_start': (now + timedelta(days=settings.MAX_BOOKING_DAYS_AHEAD)).strftime(DT_FORMAT),
    })
 
@require_POST
@role_required('client')
def book(request):
    room_id = _int(request.POST.get('room_id'), 0)
    back_params = {
        'tariff': request.POST.get('tariff_id', ''),
        'units': request.POST.get('units', '1'),
        'start': request.POST.get('start', ''),
    }
    try:
        queries.create_booking(
            account_id=request.user.id,
            pc_id=_int(request.POST.get('pc_id'), 0),
            tariff_id=_int(request.POST.get('tariff_id'), 0),
            units=request.POST.get('units'),
            start=_parse_dt(request.POST.get('start')),
        )
    except ServiceError as e:
        messages.error(request, str(e))
        url = reverse('zone_detail', args=[room_id]) if room_id else reverse('zones')
        return redirect(f'{url}?{urlencode(back_params)}')
    messages.success(request, 'Место забронировано.')
    return redirect('my_reserves')
 
@role_required('client')
def my_reserves(request):
    return render(request, 'booking/my_reserves.html', {
        'reserves': queries.list_reserves(account_id=request.user.id),
    })
 
@require_POST
@role_required('client')
def cancel_reserve(request):
    """Общий обработчик отмены: права клиента / админа проверяются в queries."""
    try:
        queries.cancel_reserve(request.POST.get('reserve_id'), request.user)
        messages.success(request, 'Бронь отменена.')
    except ServiceError as e:
        messages.error(request, str(e))
    fallback = 'staff_reserves' if request.user.is_club_admin else 'my_reserves'
    return redirect(_safe_next(request, fallback))

@role_required('admin')
def staff_reserves(request):
    return render(request, 'booking/staff/reserves.html', {
        'reserves': queries.list_reserves(only_active=request.GET.get('all') != '1'),
        'show_all': request.GET.get('all') == '1',
    })
 
@require_POST
@role_required('admin')
def staff_extend(request):
    try:
        queries.extend_booking_item(
            request.POST.get('item_id'), request.POST.get('units', 1)
        )
        messages.success(request, 'Время добавлено.')
    except ServiceError as e:
        messages.error(request, str(e))
    return redirect('staff_reserves')
 
@role_required('admin')
def staff_accounts(request):
    return render(request, 'booking/staff/accounts.html', {
        'accounts': queries.list_accounts(),
    })
 
@require_POST
@role_required('admin')
def staff_set_active(request):
    active = request.POST.get('active') == '1'
    try:
        cancelled = queries.set_account_active(
            request.POST.get('account_id'), active, request.user
        )
        if active:
            messages.success(request, 'Аккаунт разблокирован.')
        else:
            messages.success(
                request, f'Аккаунт заблокирован. Отменено будущих броней: {cancelled}.'
            )
    except ServiceError as e:
        messages.error(request, str(e))
    return redirect('staff_accounts')
 
@require_POST
@role_required('superuser')
def staff_set_role(request):
    try:
        queries.set_account_role(
            request.POST.get('account_id'), request.POST.get('role'), request.user
        )
        messages.success(request, 'Роль изменена.')
    except ServiceError as e:
        messages.error(request, str(e))
    return redirect('staff_accounts')

@role_required('superuser')
def editor(request):
    return render(request, 'booking/editor.html', {
        'place': queries.get_place(),
        'rooms': queries.list_rooms(),
        'pcs': queries.list_all_pcs(),
        'specs': queries.list_specs(),
    })
 
def _api(handler):
    """JSON POST-эндпоинт редактора: единая обработка ошибок."""
    @require_POST
    @role_required('superuser', api=True)
    def view(request, *args, **kwargs):
        try:
            result = handler(_json_body(request), *args, **kwargs)
        except ServiceError as e:
            return JsonResponse({'error': str(e)}, status=400)
        return JsonResponse({'ok': True, **(result or {})})
    view.__name__ = handler.__name__
    return view
 
@_api
def api_place_points(data, place_id):
    queries.set_place_points(place_id, data.get('points'))
 
@_api
def api_room_points(data, room_id):
    queries.set_room_points(room_id, data.get('points'))
 
@_api
def api_pc_move(data, pc_id):
    queries.move_pc(pc_id, data.get('x'), data.get('y'), data.get('rotation', 0))
 
@_api
def api_pc_status(data, pc_id):
    queries.set_pc_status(pc_id, data.get('status'))
 
@_api
def api_room_create(data):
    place = queries.get_place()
    if place is None:
        raise ServiceError('Сначала создайте помещение.')
    return {'id': queries.create_room(
        place['id_place'], data.get('name'), data.get('description'))}
 
@_api
def api_pc_create(data):
    return {'id': queries.create_pc(
        data.get('room_id'), data.get('spec_id'), data.get('number'),
        data.get('status', queries.PC_READY))}
 
@_api
def api_tariff_create(data):
    return {'id': queries.create_tariff(
        data.get('room_id'), data.get('name'), data.get('unit_price'),
        data.get('duration_minutes'), data.get('description'))}
 
@_api
def api_spec_create(data):
    for field in ('cpu', 'gpu', 'ram', 'monitor'):
        if not (data.get(field) or '').strip():
            raise ServiceError('Заполните CPU, GPU, RAM и монитор.')
    return {'id': queries.create_spec(
        data['cpu'], data['gpu'], data['ram'], data['monitor'],
        data.get('mouse'), data.get('keyboard'), data.get('headphones'), data.get('chair'))}