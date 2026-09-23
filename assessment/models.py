from django.db import models, transaction
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.models import User
from django.apps import apps


class AwardCycle(models.Model):
    year = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=255)
    is_open = models.BooleanField(default=False)
    excel_file = models.FileField(upload_to='cycles/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-year']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.is_open:
                AwardCycle.objects.exclude(pk=self.pk).update(is_open=False)
            super().save(*args, **kwargs)
            if self.is_open:
                Organization = apps.get_model('accounts', 'Organization')
                for org in Organization.objects.filter(is_active=True):
                    Questionnaire.objects.get_or_create(cycle=self, organization=org)


class AssessmentCategory(models.Model):
    cycle = models.ForeignKey(AwardCycle, on_delete=models.CASCADE, related_name='categories')
    code = models.CharField(max_length=20, blank=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    weight = models.DecimalField(max_digits=8, decimal_places=6, default=0)
    assessment_profile = models.CharField(max_length=30, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_informal_sector_only = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Assessment Category"
        verbose_name_plural = "Assessment Categories"
        ordering = ['order', 'name']

    def __str__(self):
        return f"{self.cycle.name} — {self.name}"


class Criterion(models.Model):
    category = models.ForeignKey(AssessmentCategory, on_delete=models.CASCADE, related_name='criteria')
    number = models.CharField(max_length=50)
    name = models.CharField(max_length=1000)
    description = models.TextField(blank=True)
    area_code = models.CharField(max_length=50, blank=True)
    assessment_area = models.CharField(max_length=500, blank=True)
    assessment_criterion_code = models.CharField(max_length=50, blank=True)
    assessment_criterion = models.TextField(blank=True)
    regulation = models.TextField(blank=True)
    weight = models.DecimalField(max_digits=10, decimal_places=8, default=0)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_numeric = models.BooleanField(default=False)
    numeric_fields = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category__order', 'order', 'number']
        unique_together = ['category', 'number']

    def __str__(self):
        return f"[{self.category.name}] #{self.number}: {self.name[:80]}"


class LevelIndicator(models.Model):
    criterion = models.ForeignKey(Criterion, on_delete=models.CASCADE, related_name='levels')
    level = models.PositiveIntegerField(validators=[MinValueValidator(0), MaxValueValidator(5)])
    indicator = models.TextField()

    class Meta:
        ordering = ['criterion', 'level']
        unique_together = ['criterion', 'level']

    def __str__(self):
        return f"{self.criterion.name[:50]} — Level {self.level}"


class Questionnaire(models.Model):
    cycle = models.ForeignKey(AwardCycle, on_delete=models.CASCADE, related_name='questionnaires')
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='questionnaires'
    )
    is_submitted = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)
    is_distributed = models.BooleanField(default=False)
    distributed_at = models.DateTimeField(null=True, blank=True)

    # Workflow state for organizations configured to require a judging stage.
    judging_completed = models.BooleanField(default=False)

    judging_comments = models.TextField(
        blank=True,
        default='',
        help_text='Overall comments provided by the Judge.'
    )

    judged_at = models.DateTimeField(null=True, blank=True)

    judged_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='judged_questionnaires',
    )
    distributed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='distributed_reports'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-cycle__year', 'organization__name']
        unique_together = ['cycle', 'organization']

    def __str__(self):
        return f"{self.cycle.name} — {self.organization.name}"

    @property
    def completion_percentage(self):
        is_informal = self.organization.org_type == 'informal_sector'
        total = Criterion.objects.filter(
            category__cycle=self.cycle,
            category__is_informal_sector_only=is_informal,
            is_active=True,
        ).count()
        if total == 0:
            return 0
        answered = (
            self.responses.filter(score__isnull=False).count()
            + self.responses.filter(
                criterion__is_numeric=True,
                numeric_data__isnull=False,
                score__isnull=True,
            ).count()
        )
        return round((answered / total) * 100, 1)


class Response(models.Model):
    questionnaire = models.ForeignKey(Questionnaire, on_delete=models.CASCADE, related_name='responses')
    criterion = models.ForeignKey(Criterion, on_delete=models.CASCADE, related_name='responses')
    score = models.PositiveIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(5)], null=True, blank=True
    )
    response = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True)
    numeric_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['questionnaire', 'criterion']
        ordering = ['criterion__category__order', 'criterion__order']

    def __str__(self):
        return f"{self.questionnaire} — {self.criterion.name[:50]}: {self.score}"



import os as _os_models
import re as _re_models
import uuid as _uuid_models


def evidence_upload_path(instance, filename):
    safe = _re_models.sub(r'[^\w.\-]', '_', _os_models.path.basename(filename))
    return f'evidence/{instance.organization_id}/{_uuid_models.uuid4().hex}_{safe}'


class EvidenceDocument(models.Model):
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='evidence_documents'
    )
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to=evidence_upload_path)
    file_size = models.PositiveIntegerField(default=0)
    original_filename = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='uploaded_evidence'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.organization.name} — {self.title}"


class EvidenceLink(models.Model):
    response = models.ForeignKey(
        Response, on_delete=models.CASCADE, related_name='evidence_links'
    )
    document = models.ForeignKey(
        EvidenceDocument, on_delete=models.CASCADE, related_name='evidence_links'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['response', 'document']

    def __str__(self):
        return f"{self.response} → {self.document}"


class JudgeResponse(models.Model):
    """A judge's private, criterion-level score and comment.

    Each judge gets an independent row. Views never expose another judge's
    rows; the Secretariat/admin report reveals them only after the cycle closes.
    """
    questionnaire = models.ForeignKey(Questionnaire, on_delete=models.CASCADE, related_name='judge_responses')
    judge = models.ForeignKey(User, on_delete=models.CASCADE, related_name='judge_responses')
    criterion = models.ForeignKey(Criterion, on_delete=models.CASCADE, related_name='judge_responses')
    score = models.PositiveIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(5)], null=True, blank=True
    )
    notes = models.TextField(blank=True)
    excel_attachment = models.FileField(
        upload_to='judge_attachments/',
        blank=True,
        null=True,
        help_text='Optional Excel attachment for this criterion (.xlsx or .xls).',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['questionnaire', 'judge', 'criterion']
        ordering = ['criterion__category__order', 'criterion__order']
        indexes = [
            models.Index(fields=['questionnaire', 'criterion']),
            models.Index(fields=['judge', 'questionnaire']),
        ]

    def __str__(self):
        return f"Judge {self.judge.username} — {self.questionnaire} — {self.criterion.name[:50]}: {self.score}"


class VerifierResponse(models.Model):
    questionnaire = models.ForeignKey(Questionnaire, on_delete=models.CASCADE, related_name='verifier_responses')
    verifier = models.ForeignKey(User, on_delete=models.CASCADE, related_name='verifier_responses')
    criterion = models.ForeignKey(Criterion, on_delete=models.CASCADE, related_name='verifier_responses')
    score = models.PositiveIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(5)], null=True, blank=True
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['questionnaire', 'verifier', 'criterion']
        ordering = ['criterion__category__order', 'criterion__order']

    def __str__(self):
        return f"Verifier {self.verifier.username} — {self.questionnaire} — {self.criterion.name[:50]}: {self.score}"


class StageSubmission(models.Model):
    """Tracks explicit Save/Submit state for Secretariat and Judges.

    Secretariat submissions are per category; Judge submissions are for the
    whole questionnaire (category is NULL). A submitted stage is locked for
    that user until the cycle is closed/reopened by the normal workflow.
    """
    STAGE_CHOICES = [
        ('secretariat', 'Secretariat'),
        ('judge', 'Judge'),
    ]

    questionnaire = models.ForeignKey(
        Questionnaire, on_delete=models.CASCADE, related_name='stage_submissions'
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='stage_submissions'
    )
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES)
    category = models.ForeignKey(
        AssessmentCategory, on_delete=models.CASCADE, null=True, blank=True,
        related_name='stage_submissions'
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['stage', 'category__order', 'updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['questionnaire', 'user', 'stage', 'category'],
                name='uniq_stage_submission_with_category',
            ),
            models.UniqueConstraint(
                fields=['questionnaire', 'user', 'stage'],
                condition=models.Q(category__isnull=True),
                name='uniq_stage_submission_without_category',
            ),
        ]

    @property
    def is_submitted(self):
        return self.submitted_at is not None

    def __str__(self):
        scope = self.category.name if self.category else 'questionnaire'
        return f"{self.stage} — {self.user.username} — {scope}"


def categories_for_org(cycle, org, *, is_active=True):
    """Return the applicable AssessmentCategory queryset for this org's type.

    Informal Sector orgs receive only is_informal_sector_only=True categories.
    All other org types receive only is_informal_sector_only=False categories.
    """
    is_informal = org.org_type == 'informal_sector'
    qs = cycle.categories.filter(is_informal_sector_only=is_informal)
    if getattr(org, 'assessment_profile', ''):
        qs = qs.filter(assessment_profile=org.assessment_profile)
    if is_active:
        qs = qs.filter(is_active=True)
    return qs.order_by('order')
