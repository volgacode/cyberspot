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