from django.shortcuts import render
from django.core.paginator import Paginator
from django.contrib.auth.models import User
from accounts.decorators import role_required
from accounts.models import Organization
from .models import AuditLog


@role_required('admin')
def audit_log_view(request):
    qs = AuditLog.objects.select_related('user', 'organization')

    user_id   = request.GET.get('user', '')
    action    = request.GET.get('action', '')
    org_id    = request.GET.get('organization', '')
    date_from = request.GET.get('date_from', '')
    date_to   = request.GET.get('date_to', '')

    if user_id and user_id.isdigit():   qs = qs.filter(user_id=user_id)
    if action:                           qs = qs.filter(action=action)
    if org_id and org_id.isdigit():     qs = qs.filter(organization_id=org_id)
    if date_from:                        qs = qs.filter(timestamp__date__gte=date_from)
    if date_to:                          qs = qs.filter(timestamp__date__lte=date_to)

    paginator = Paginator(qs, 50)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'audit/audit_log.html', {
        'page_obj': page_obj,
        'users': User.objects.filter(audit_logs__isnull=False).distinct().order_by('username'),
        'organizations': Organization.objects.all().order_by('name'),
        'action_choices': AuditLog.ACTION_CHOICES,
        'filters': {
            'user': user_id,
            'action': action,
            'organization': org_id,
            'date_from': date_from,
            'date_to': date_to,
        },
    })
