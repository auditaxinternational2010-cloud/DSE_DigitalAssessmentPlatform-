from django.db import models
from django.contrib.auth.models import User


def _get_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('request.approved',        'Request Approved'),
        ('request.rejected',        'Request Rejected'),
        ('request.reopened',        'Request Reopened'),
        ('cycle.opened',            'Cycle Opened'),
        ('cycle.closed',            'Cycle Closed'),
        ('user.created',            'User Created'),
        ('user.deleted',            'User Deleted'),
        ('user.edited',            'User Edited'),
        ('email.welcome_resent',    'Welcome email resent'),
        ('org.created',             'Organization Created'),
        ('org.deleted',             'Organization Deleted'),
        ('questionnaire.submitted', 'Questionnaire Submitted'),
        ('verifier.scores_saved',   'Verifier Scores Saved'),
        ('report.distributed',      'Report Distributed'),
        ('report.revoked',          'Report Revoked'),
        ('sharelink.created',       'Share Link Created'),
        ('sharelink.revoked',       'Share Link Revoked'),
    ]

    user         = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='audit_logs'
    )
    action       = models.CharField(max_length=50, choices=ACTION_CHOICES)
    description  = models.TextField()
    object_type  = models.CharField(max_length=50, blank=True)
    object_id    = models.PositiveIntegerField(null=True, blank=True)
    object_repr  = models.CharField(max_length=255, blank=True)
    organization = models.ForeignKey(
        'accounts.Organization', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='audit_logs'
    )
    timestamp    = models.DateTimeField(auto_now_add=True)
    ip_address   = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['action']),
        ]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} — {self.get_action_display()} by {self.user}"

    @classmethod
    def log(cls, request, action, description,
            object_repr='', object_type='', object_id=None, organization=None):
        cls.objects.create(
            user=request.user if request.user.is_authenticated else None,
            action=action,
            description=description,
            object_type=object_type,
            object_id=object_id,
            object_repr=object_repr,
            organization=organization,
            ip_address=_get_ip(request),
        )
