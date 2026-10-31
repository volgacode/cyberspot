from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden, JsonResponse

from .models import ROLE_LEVEL


def role_required(min_role, api=False):
    """
    Пускает пользователей с ролью не ниже min_role
    (client < admin < superuser).
    Аноним -> редирект на логин (для api=True — JSON 401);
    не хватает прав -> 403.
    """
    need = ROLE_LEVEL[min_role]

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                if api:
                    return JsonResponse({'error': 'Нужно войти в аккаунт.'}, status=401)
                return redirect_to_login(request.get_full_path())
            if user.level < need:
                if api:
                    return JsonResponse({'error': 'Недостаточно прав.'}, status=403)
                return HttpResponseForbidden('Недостаточно прав.')
            return view(request, *args, **kwargs)
        return wrapper
    return decorator