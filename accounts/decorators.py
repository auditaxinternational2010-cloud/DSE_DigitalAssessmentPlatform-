from functools import wraps
from django.shortcuts import redirect


def role_required(*roles):
    """Restrict view to users whose UserProfile.role is in `roles`."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            try:
                profile = request.user.userprofile
            except Exception:
                return redirect('login')
            if profile.role not in roles:
                return redirect('dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
