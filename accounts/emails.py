import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from .models import EmailLog

logger = logging.getLogger(__name__)


def _send_and_log(kind, subject, message, recipients, *,
                  user=None, organization=None, triggered_by=None):
    """Send one email and record exactly one EmailLog row.

    Writes a row whether the send succeeds or fails, then re-raises on failure —
    callers rely on catching the exception. A 'sent' row means the SMTP server
    accepted the message; it is not proof of delivery.
    """
    status, error = 'sent', ''
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, recipients,
                  fail_silently=False)
    except Exception as exc:
        status, error = 'failed', repr(exc)
        raise
    finally:
        try:
            EmailLog.objects.create(
                kind=kind,
                recipient=', '.join(recipients),
                subject=subject,
                status=status,
                error=error,
                user=user,
                organization=organization,
                triggered_by=triggered_by,
            )
        except Exception:
            # Never let bookkeeping break (or mask) the send itself.
            logger.exception('Failed to write EmailLog row for %s → %s', kind, recipients)


def send_welcome_email(user, password, *, triggered_by=None):
    login_url = settings.SITE_URL.rstrip('/') + '/login/'
    subject = 'Welcome to the EYA Platform — Your Login Credentials'
    message = render_to_string('accounts/email/welcome.txt', {
        'user': user,
        'password': password,
        'login_url': login_url,
    })
    organization = getattr(getattr(user, 'userprofile', None), 'organization', None)
    _send_and_log('welcome', subject, message, [user.email],
                  user=user, organization=organization, triggered_by=triggered_by)


def send_new_request_notification(pr):
    """Email admins that a new ParticipationRequest arrived.

    Recipients are settings.ADMIN_NOTIFY_EMAILS when that override is set,
    otherwise every admin-role user with an email address. Raises on SMTP
    failure — the caller is responsible for catching so a mail outage never
    breaks a public applicant's submission.
    """
    from django.contrib.auth.models import User

    recipients = list(settings.ADMIN_NOTIFY_EMAILS)
    if not recipients:
        recipients = list(
            User.objects.filter(userprofile__role='admin')
            .exclude(email='')
            .values_list('email', flat=True)
        )
    if not recipients:
        return

    review_url = f"{settings.SITE_URL.rstrip('/')}/accounts/requests/{pr.pk}/"
    subject = f'New EYA participation request — {pr.org_name}'
    message = render_to_string('accounts/email/new_request_notification.txt', {
        'pr': pr,
        'review_url': review_url,
    })
    _send_and_log('new_request', subject, message, recipients)
