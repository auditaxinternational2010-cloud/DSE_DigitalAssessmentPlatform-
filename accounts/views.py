import logging
import secrets
import string
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.contrib.auth.views import PasswordChangeView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from .models import Organization, UserProfile, VerifierAssignment, ParticipationRequest, EmailLog, ORG_TYPE_SUBTYPES
from .decorators import role_required
from .emails import send_welcome_email, send_new_request_notification
from .forms import UserCreateForm, UserEditForm, OrgForm, ParticipationRequestForm, ProfileForm
from . import ratelimit
from audit.models import AuditLog

_ORG_SUBTYPES_DATA = {k: list(v) for k, v in ORG_TYPE_SUBTYPES.items()}
logger = logging.getLogger(__name__)


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = AuthenticationForm(request, data=request.POST or None)
    throttle_message = None
    if request.method == 'POST':
        fail_key = f'login-fail:{ratelimit.client_ip(request)}'
        if not settings.TESTING and ratelimit.count(fail_key) >= settings.LOGIN_RDSELIMIT_ATTEMPTS:
            throttle_message = (
                'Too many failed sign-in attempts. Please wait a few minutes and try again.'
            )
        elif form.is_valid():
            login(request, form.get_user())
            ratelimit.reset(fail_key)
            return redirect('dashboard')
        elif not settings.TESTING:
            ratelimit.hit(fail_key, settings.LOGIN_RDSELIMIT_WINDOW)
    return render(request, 'accounts/login.html', {'form': form, 'throttle_message': throttle_message})


@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')


class FirstLoginPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    template_name = 'accounts/change_password.html'
    success_url = reverse_lazy('dashboard')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['forced'] = self.request.user.userprofile.must_change_password
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        profile = self.request.user.userprofile
        profile.must_change_password = False
        profile.save(update_fields=['must_change_password'])
        messages.success(self.request, 'Password changed successfully. Welcome!')
        return response


def dashboard_view(request):
    if not request.user.is_authenticated:
        return redirect('login')
    try:
        role = request.user.userprofile.role
    except Exception:
        return redirect('login')
    if role == 'admin':
        return redirect('admin_dashboard')
    elif role == 'verifier':
        return redirect('verifier_dashboard')
    elif role == 'judge':
        return redirect('judges_dashboard')
    else:
        return redirect('member_dashboard')


@login_required
def profile_view(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Profile updated successfully.')
        return redirect('profile')
    profile = request.user.userprofile
    return render(request, 'accounts/profile.html', {
        'form': form,
        'show_org': profile.role == 'member',
        'org': profile.organization if profile.role == 'member' else None,
    })


@role_required('admin')
def user_list_view(request):
    q = request.GET.get('q', '').strip()
    qs = User.objects.select_related('userprofile', 'userprofile__organization').order_by('username')
    if q:
        qs = qs.filter(username__icontains=q)
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Attach the latest welcome-email attempt per user in one extra query,
    # not one per row.
    users = list(page_obj.object_list)
    latest = {}
    for log in EmailLog.objects.filter(kind='welcome', user__in=users).order_by('-created_at'):
        latest.setdefault(log.user_id, log)
    for u in users:
        u.welcome_email_log = latest.get(u.pk)
    page_obj.object_list = users

    return render(request, 'accounts/user_list.html', {'page_obj': page_obj, 'q': q})


@role_required('admin')
def user_create_view(request):
    form = UserCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            user = form.save()
        AuditLog.log(request, 'user.created',
            f'Created user "{user.username}" with role {user.userprofile.role}',
            object_type='User', object_id=user.pk, object_repr=user.username)
        messages.success(request, f'User {user.username} created.')
        return redirect('user_list')
    return render(request, 'accounts/user_form.html', {'form': form, 'action': 'Create'})


@role_required('admin')
def user_edit_view(request, pk):
    user = get_object_or_404(User, pk=pk)
    form = UserEditForm(request.POST or None, instance=user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        AuditLog.log(request, 'user.edited',
            f'Edited user "{user.username}"',
            object_type='User', object_id=user.pk, object_repr=user.username)
        messages.success(request, f'User {user.username} updated.')
        return redirect('user_list')
    return render(request, 'accounts/user_form.html', {'form': form, 'action': 'Edit', 'edit_user': user})


@role_required('admin')
def user_delete_view(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, 'You cannot delete your own account.')
        return redirect('user_list')
    if request.method == 'POST':
        username = user.username
        user_pk = user.pk
        user.delete()
        AuditLog.log(request, 'user.deleted',
            f'Deleted user "{username}"',
            object_type='User', object_id=user_pk, object_repr=username)
        messages.success(request, f'User {username} deleted.')
        return redirect('user_list')
    return redirect('user_list')


@role_required('admin')
def email_log_view(request):
    qs = EmailLog.objects.select_related('user', 'organization', 'triggered_by')

    kind      = request.GET.get('kind', '')
    status    = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to   = request.GET.get('date_to', '')

    if kind:   qs = qs.filter(kind=kind)
    if status: qs = qs.filter(status=status)
    if date_from and parse_date(date_from): qs = qs.filter(created_at__date__gte=date_from)
    if date_to and parse_date(date_to):     qs = qs.filter(created_at__date__lte=date_to)

    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'accounts/email_log.html', {
        'page_obj': page_obj,
        'kind_choices': EmailLog.KIND_CHOICES,
        'status_choices': EmailLog.STATUS_CHOICES,
        'filters': {
            'kind': kind,
            'status': status,
            'date_from': date_from,
            'date_to': date_to,
        },
    })


@role_required('admin')
def org_list_view(request):
    q = request.GET.get('q', '').strip()
    qs = Organization.objects.prefetch_related('member_profiles__user', 'verifier_assignments__verifier').order_by('name')
    if q:
        qs = qs.filter(name__icontains=q)
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'accounts/org_list.html', {'page_obj': page_obj, 'q': q})


@role_required('admin')
def org_create_view(request):
    form = OrgForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        org = form.save()
        AuditLog.log(request, 'org.created',
            f'Created organization "{org.name}"',
            object_type='Organization', object_id=org.pk, object_repr=org.name,
            organization=org)
        messages.success(request, f'Organization {org.name} created.')
        return redirect('org_list')
    return render(request, 'accounts/org_form.html', {
        'form': form,
        'action': 'Create',
        'subtypes_data': _ORG_SUBTYPES_DATA,
    })


@role_required('admin')
def org_edit_view(request, pk):
    org = get_object_or_404(Organization, pk=pk)
    form = OrgForm(request.POST or None, instance=org)
    if request.method == 'POST' and form.is_valid():
        form.save()
        from assessment.models import AwardCycle, Questionnaire
        open_cycle = AwardCycle.objects.filter(is_open=True).first()
        if open_cycle:
            if org.is_active:
                Questionnaire.objects.get_or_create(cycle=open_cycle, organization=org)
            else:
                Questionnaire.objects.filter(organization=org, cycle=open_cycle).delete()
        messages.success(request, f'Organization {org.name} updated.')
        return redirect('org_list')
    return render(request, 'accounts/org_form.html', {
        'form': form,
        'action': 'Edit',
        'org': org,
        'subtypes_data': _ORG_SUBTYPES_DATA,
    })


@role_required('admin')
def org_delete_view(request, pk):
    org = get_object_or_404(Organization, pk=pk)
    if request.method == 'POST':
        org_name = org.name
        org_pk = org.pk
        member = org.member
        if member:
            member.delete()
        org.delete()
        AuditLog.log(request, 'org.deleted',
            f'Deleted organization "{org_name}"',
            object_type='Organization', object_id=org_pk, object_repr=org_name)
        messages.success(request, f'Organization "{org_name}" and its member user deleted.')
        return redirect('org_list')
    return redirect('org_list')


def participation_request_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = ParticipationRequestForm(request.POST or None)
    if request.method == 'POST':
        over_limit = (
            not settings.TESTING
            and ratelimit.hit(f'preq:{ratelimit.client_ip(request)}',
                              settings.PARTICIPATION_RDSELIMIT_WINDOW)
            > settings.PARTICIPATION_RDSELIMIT_ATTEMPTS
        )
        valid = form.is_valid()
        if valid and not over_limit:
            # Empty honeypot → genuine submission. A filled one is a bot: accept
            # silently (so it can't tell it was caught) but never persist it.
            if not form.cleaned_data.get('website'):
                pr = form.save()
                try:
                    send_new_request_notification(pr)
                except Exception:
                    # A mail outage must never break a public applicant's
                    # submission. The request is saved; the admin will see it
                    # in the request list regardless.
                    logger.exception(
                        'Failed to send new-request notification for request %s', pr.pk)
            return redirect('request_submitted')
        if over_limit:
            form.add_error(None, 'Too many requests from your network. Please try again later.')
    return render(request, 'accounts/participation_request.html', {
        'form': form,
        'subtypes_data': _ORG_SUBTYPES_DATA,
    })


def request_submitted_view(request):
    return render(request, 'accounts/request_submitted.html')


def _generate_password(length=12):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


@role_required('admin')
def request_list_view(request):
    status_filter = request.GET.get('status', '')
    qs = ParticipationRequest.objects.select_related('reviewed_by')
    if status_filter in ('pending', 'approved', 'rejected'):
        qs = qs.filter(status=status_filter)
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'accounts/request_list.html', {
        'page_obj': page_obj,
        'status_filter': status_filter,
    })


@role_required('admin')
def request_detail_view(request, pk):
    pr = get_object_or_404(ParticipationRequest, pk=pk)
    return render(request, 'accounts/request_detail.html', {'pr': pr})


@role_required('admin')
def request_approve_view(request, pk):
    pr = get_object_or_404(ParticipationRequest, pk=pk)
    if request.method == 'POST':
        with transaction.atomic():
            pr = ParticipationRequest.objects.select_for_update().get(pk=pk)
            if pr.status != 'pending':
                messages.error(request, 'This request has already been reviewed.')
                return redirect('request_detail', pk=pk)
            if Organization.objects.filter(name=pr.org_name).exists():
                messages.error(request, f'An organization named "{pr.org_name}" already exists. Resolve the conflict before approving.')
                return redirect('request_detail', pk=pk)
            if User.objects.filter(username=pr.email).exists():
                messages.error(request, f'A user with email "{pr.email}" already exists. Resolve the conflict before approving.')
                return redirect('request_detail', pk=pk)
            password = _generate_password()
            org = Organization.objects.create(
                name=pr.org_name,
                org_type=pr.org_type,
                org_subtype=pr.org_subtype,
                org_subtype_other=pr.org_subtype_other,
                region=pr.region,
                physical_address=pr.physical_address,
                postal_address=pr.postal_address,
                num_employees=pr.num_employees,
                investment_capital=pr.investment_capital,
            )
            user = User.objects.create_user(
                username=pr.email,
                email=pr.email,
                password=password,
                first_name=pr.first_name,
                last_name=pr.last_name,
            )
            UserProfile.objects.create(
                user=user,
                role='member',
                organization=org,
                must_change_password=True,
                phone_number=pr.phone_number,
            )
            pr.status = 'approved'
            pr.reviewed_at = timezone.now()
            pr.reviewed_by = request.user
            pr.save()
        try:
            send_welcome_email(user, password, triggered_by=request.user)
        except Exception:
            messages.warning(
                request,
                'User account created but the welcome email could not be sent. '
                'Please share the credentials below with the user directly.'
            )
        try:
            AuditLog.log(request, 'request.approved',
                f'Approved participation request from "{org.name}" — created user {user.username}',
                object_type='Organization', object_id=org.pk, object_repr=org.name,
                organization=org)
        except Exception:
            pass
        request.session['approval_credentials'] = {
            'org_name': org.name,
            'username': user.username,
            'password': password,
            'email': pr.email,
        }
        return redirect('request_approval_success')
    return redirect('request_detail', pk=pk)


@role_required('admin')
def request_approval_success_view(request):
    credentials = request.session.pop('approval_credentials', None)
    if not credentials:
        return redirect('request_list')
    return render(request, 'accounts/approval_success.html', {'credentials': credentials})


@role_required('admin')
@require_POST
def resend_welcome_email_view(request, pk):
    """Reissue a member's welcome email with a freshly generated password.

    The original password was hashed and discarded at approval time, so a resend
    necessarily issues new credentials and invalidates the old ones. The email
    template says so explicitly.
    """
    user = get_object_or_404(User, pk=pk)
    profile = getattr(user, 'userprofile', None)
    if profile is None or profile.role != 'member':
        messages.error(request, 'Welcome emails can only be resent to member accounts.')
        return redirect('user_list')

    password = _generate_password()
    with transaction.atomic():
        user.set_password(password)
        user.save(update_fields=['password'])
        profile.must_change_password = True
        profile.save(update_fields=['must_change_password'])

    send_failed = False
    try:
        send_welcome_email(user, password, triggered_by=request.user)
        messages.success(request, f'Welcome email resent to {user.email} with new credentials.')
    except Exception:
        send_failed = True
        messages.warning(
            request,
            'New credentials were issued but the welcome email could not be sent. '
            'Please share the credentials below with the user directly.'
        )
        request.session['approval_credentials'] = {
            'org_name': profile.organization.name if profile.organization else '',
            'username': user.username,
            'password': password,
            'email': user.email,
        }

    try:
        AuditLog.log(request, 'email.welcome_resent',
            f'Resent welcome email to {user.username} with newly issued credentials',
            object_type='User', object_id=user.pk, object_repr=user.username,
            organization=profile.organization)
    except Exception:
        pass

    # Branch on what *this* request did, not on the session: request_approve_view
    # also writes 'approval_credentials' and only request_approval_success_view
    # pops it, so a stale key from an abandoned approval would otherwise divert a
    # successful resend to a page showing another org's credentials.
    if send_failed:
        return redirect('request_approval_success')
    return redirect('user_list')


@role_required('admin')
def request_reject_view(request, pk):
    pr = get_object_or_404(ParticipationRequest, pk=pk)
    if request.method == 'POST':
        with transaction.atomic():
            pr = ParticipationRequest.objects.select_for_update().get(pk=pk)
            if pr.status != 'pending':
                messages.error(request, 'This request has already been reviewed.')
                return redirect('request_detail', pk=pk)
            pr.status = 'rejected'
            pr.reviewed_at = timezone.now()
            pr.reviewed_by = request.user
            pr.save()
        AuditLog.log(request, 'request.rejected',
            f'Rejected participation request from "{pr.org_name}"',
            object_type='ParticipationRequest', object_id=pr.pk, object_repr=pr.org_name)
        messages.success(request, f'Request from "{pr.org_name}" has been rejected.')
        return redirect('request_list')
    return redirect('request_detail', pk=pk)


@role_required('admin')
def request_reopen_view(request, pk):
    pr = get_object_or_404(ParticipationRequest, pk=pk)
    if request.method == 'POST':
        with transaction.atomic():
            pr = ParticipationRequest.objects.select_for_update().get(pk=pk)
            if pr.status != 'rejected':
                messages.error(request, 'Only rejected requests can be reopened.')
                return redirect('request_detail', pk=pk)
            pr.status = 'pending'
            pr.reviewed_by = None
            pr.reviewed_at = None
            pr.save()
        AuditLog.log(request, 'request.reopened',
            f'Reopened participation request from "{pr.org_name}" to pending',
            object_type='ParticipationRequest', object_id=pr.pk, object_repr=pr.org_name)
        messages.success(request, f'Request from "{pr.org_name}" has been reopened.')
        return redirect('request_detail', pk=pk)
    return redirect('request_detail', pk=pk)
