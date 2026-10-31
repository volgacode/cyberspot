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