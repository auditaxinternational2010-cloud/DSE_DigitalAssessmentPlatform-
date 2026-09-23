from django.core.exceptions import ObjectDoesNotExist
from accounts.models import ParticipationRequest


def eya_nav(request):
    if not request.user.is_authenticated:
        return {}
    try:
        profile = request.user.userprofile
    except ObjectDoesNotExist:
        return {}

    ctx = {}
    if profile.role == 'admin':
        ctx['pending_request_count'] = ParticipationRequest.objects.filter(
            status='pending'
        ).count()
    return ctx
