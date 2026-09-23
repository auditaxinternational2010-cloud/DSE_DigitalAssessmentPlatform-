"""Workflow coverage helpers.

Secretariat no longer scores submitted questionnaires. Completion is therefore
based on the explicit per-category Secretariat submission state.
"""
def _submitted_category_ids(questionnaire):
    from .models import StageSubmission
    return set(
        StageSubmission.objects.filter(
            questionnaire=questionnaire,
            stage='secretariat',
            submitted_at__isnull=False,
        ).values_list('category_id', flat=True)
    )

def criterion_coverage(questionnaire, criteria):
    """Map criterion id -> submitted Secretariat information."""
    from .models import StageSubmission
    category_ids = {c.category_id for c in criteria}
    rows = (
        StageSubmission.objects
        .filter(
            questionnaire=questionnaire,
            stage='secretariat',
            submitted_at__isnull=False,
            category_id__in=category_ids,
        )
        .select_related('user')
        .order_by('submitted_at')
    )
    result = {}
    for row in rows:
        for criterion in criteria:
            if criterion.category_id == row.category_id:
                result.setdefault(criterion.id, []).append({
                    'verifier_id': row.user_id,
                    'name': row.user.get_full_name() or row.user.username,
                    'at': row.submitted_at,
                })
    return result

def category_coverage(questionnaire):
    from .models import categories_for_org, Criterion
    categories = list(categories_for_org(questionnaire.cycle, questionnaire.organization))
    submitted = _submitted_category_ids(questionnaire)
    result = {}
    for cat in categories:
        total = Criterion.objects.filter(category=cat, is_active=True).count()
        result[cat.id] = (total if cat.id in submitted else 0, total)
    return result

def questionnaire_coverage(questionnaires):
    from .models import categories_for_org, Criterion
    questionnaires = list(questionnaires)
    result = {}
    for q in questionnaires:
        cats = list(categories_for_org(q.cycle, q.organization))
        submitted = _submitted_category_ids(q)
        total = Criterion.objects.filter(
            category__in=cats, category__is_active=True, is_active=True
        ).count()
        covered = sum(
            Criterion.objects.filter(category=cat, is_active=True).count()
            for cat in cats if cat.id in submitted
        )
        result[q.pk] = (covered, total)
    return result
