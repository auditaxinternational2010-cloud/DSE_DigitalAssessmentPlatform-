import secrets

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


def generate_token():
    """43-character URL-safe token — 256 bits of entropy, not guessable."""
    return secrets.token_urlsafe(32)


class ShareLink(models.Model):
    """A revocable, optionally expiring public URL to the live status dashboard.

    Anyone holding the token can read the dashboard without an account, so the
    token is the credential: 256 bits, exact-match lookup, and invalid tokens
    must 404 (never 403, which would confirm the token exists).
    """
    token = models.CharField(max_length=64, unique=True, db_index=True, default=generate_token)
    label = models.CharField(max_length=255, help_text='Who this link was issued to.')
    include_contacts = models.BooleanField(
        default=False,
        help_text='Include member name, position, phone and email in the shared view.',
    )
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='share_links',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_viewed_at = models.DateTimeField(null=True, blank=True)
    view_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.label} ({"active" if self.is_valid else "inactive"})'

    @property
    def is_valid(self):
        return self.is_active and (self.expires_at is None or self.expires_at > timezone.now())
