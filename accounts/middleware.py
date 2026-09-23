from django.shortcuts import redirect

from .models import UserProfile

EXEMPT_PREFIXES = (
    '/change-password/',
    '/logout/',
    '/login/',
    '/password-reset/',
    '/accounts/profile/',
    # Public share dashboard — an authenticated admin who owes a password
    # change must not be bounced off a page that needs no account at all.
    '/share/',
)


class MustChangePasswordMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            if not any(request.path.startswith(p) for p in EXEMPT_PREFIXES):
                try:
                    if request.user.userprofile.must_change_password:
                        return redirect('change_password')
                except UserProfile.DoesNotExist:
                    pass
        return self.get_response(request)
