"""Public, token-guarded views for the live status dashboard.

Security notes:
  * The token IS the credential. Every invalid case (unknown, revoked,
    expired) raises Http404 — a 403 would confirm the token exists.
  * Contact details are gated in build_submission_report, not here, so the
    JSON endpoint cannot leak them independently of the HTML page.
"""
from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts import ratelimit
from accounts.decorators import role_required
from audit.models import AuditLog

from .forms import ShareLinkForm
from .models import ShareLink
from .reporting import build_submission_report


def _throttled(request):
    if settings.TESTING:
        return False
    key = f'share:{ratelimit.client_ip(request)}'
    return ratelimit.hit(key, settings.SHARE_RDSELIMIT_WINDOW) > settings.SHARE_RDSELIMIT_ATTEMPTS


def _get_valid_link(token):
    link = ShareLink.objects.filter(token=token).first()
    if link is None or not link.is_valid:
        raise Http404
    return link


def _harden(response):
    response['X-Robots-Tag'] = 'noindex, nofollow'
    response['Referrer-Policy'] = 'no-referrer'
    response['Cache-Control'] = 'no-store'
    return response


def public_dashboard(request, token):
    if _throttled(request):
        return _harden(HttpResponse('Too many requests', status=429))
    link = _get_valid_link(token)

    # F() so concurrent viewers don't clobber each other's increment.
    ShareLink.objects.filter(pk=link.pk).update(
        view_count=F('view_count') + 1, last_viewed_at=timezone.now())

    report = build_submission_report(include_contacts=link.include_contacts)
    response = render(request, 'share/public_dashboard.html', {
        'link': link,
        'report': report,
        'report_json': report,
        'data_url': f'/share/{token}/data/',
    })
    return _harden(response)


def public_dashboard_data(request, token):
    if _throttled(request):
        return _harden(HttpResponse('Too many requests', status=429))
    link = _get_valid_link(token)
    report = build_submission_report(include_contacts=link.include_contacts)
    return _harden(JsonResponse(report))


@role_required('admin')
def sharelink_list(request):
    links = ShareLink.objects.select_related('created_by').all()
    base = settings.SITE_URL.rstrip('/')
    return render(request, 'share/sharelink_list.html', {
        'links': links,
        'base_url': base,
    })


@role_required('admin')
def sharelink_create(request):
    form = ShareLinkForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        link = form.save(commit=False)
        link.created_by = request.user
        link.save()
        AuditLog.log(
            request, 'sharelink.created',
            f'Created share link "{link.label}" '
            f'(contacts {"included" if link.include_contacts else "hidden"})',
            object_type='ShareLink', object_id=link.pk, object_repr=link.label)
        messages.success(request, f'Share link for "{link.label}" created.')
        return redirect('sharelink_list')
    return render(request, 'share/sharelink_form.html', {'form': form})


@role_required('admin')
@require_POST
def sharelink_revoke(request, pk):
    link = get_object_or_404(ShareLink, pk=pk)
    link.is_active = False
    link.save(update_fields=['is_active'])
    AuditLog.log(
        request, 'sharelink.revoked',
        f'Revoked share link "{link.label}"',
        object_type='ShareLink', object_id=link.pk, object_repr=link.label)
    messages.success(request, f'Share link for "{link.label}" revoked.')
    return redirect('sharelink_list')
