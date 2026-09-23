"""Read-only data layer for the public status dashboard.

`build_submission_report` is a pure function: no request object, no rendering,
returns a JSON-serialisable dict. PII gating happens HERE rather than in the
template, so the JSON endpoint cannot leak contact details even by mistake.
"""
from django.utils import timezone

from accounts.models import Organization, ParticipationRequest
from assessment.models import AwardCycle, Questionnaire

# Order matters: rendered top-to-bottom in the breakdown chart.
POSITION_BUCKET_ORDER = [
    'HR / People',
    'Director / Managing',
    'Administration',
    'Other functions',
    'Unspecified',
]


def _position_bucket(position):
    """Group a free-text job title into one of POSITION_BUCKET_ORDER.

    Mirrors the bucketing the standalone HTML report did in JavaScript. Runs
    server-side because the shared view may hide positions entirely, and the
    aggregate breakdown is shown either way.
    """
    s = (position or '').strip().lower()
    if not s:
        return 'Unspecified'
    if 'director' in s and 'hr' not in s and 'human' not in s:
        return 'Director / Managing'
    if ('human resource' in s or 'hr' in s
            or 'people and culture' in s or 'human capital' in s):
        return 'HR / People'
    if 'admin' in s:
        return 'Administration'
    return 'Other functions'


def _position_by_email():
    """Map lowercased respondent email -> position, latest request winning."""
    mapping = {}
    for row in (ParticipationRequest.objects
                .order_by('submitted_at')
                .values('email', 'position')):
        email = (row['email'] or '').strip().lower()
        if email:
            mapping[email] = row['position'] or ''
    return mapping


def build_submission_report(*, include_contacts):
    open_cycle = AwardCycle.objects.filter(is_open=True).first()

    submission_map = {}
    if open_cycle:
        submission_map = {
            r['organization_id']: (r['is_submitted'], r['submitted_at'])
            for r in Questionnaire.objects
            .filter(cycle=open_cycle)
            .values('organization_id', 'is_submitted', 'submitted_at')
        }

    positions = _position_by_email()

    orgs = (Organization.objects
            .filter(is_active=True)
            .prefetch_related('member_profiles__user')
            .order_by('name'))

    rows = []
    bucket_counts = {}
    member_count = 0

    for org in orgs:
        # .all() not .filter() — filtering a prefetched manager re-queries per org.
        profile = next(
            (p for p in org.member_profiles.all() if p.role == 'member'), None)

        is_submitted, submitted_at = submission_map.get(org.pk, (False, None))
        row = {
            'org': org.name,
            'org_type': org.get_org_type_display() if org.org_type else '',
            'region': org.region,
            'submitted': bool(is_submitted),
            'submitted_at': submitted_at.isoformat() if submitted_at else None,
        }

        if profile:
            member_count += 1
            user = profile.user
            name = f'{user.first_name} {user.last_name}'.strip() or user.username
            email = (user.email or '').strip().lower()
            position = positions.get(email, '')
            phone = profile.phone_number or ''
        else:
            name = email = position = phone = ''

        bucket = _position_bucket(position)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

        if include_contacts:
            row.update({
                'name': name,
                'position': position,
                'phone': phone,
                'email': email,
            })

        rows.append(row)

    total_orgs = len(rows)
    submitted_count = sum(1 for r in rows if r['submitted'])

    return {
        'generated_at': timezone.now().isoformat(),
        'cycle': {'name': open_cycle.name, 'year': open_cycle.year} if open_cycle else None,
        'kpis': {
            'total_orgs': total_orgs,
            'submitted_count': submitted_count,
            'submission_rate': (
                round(submitted_count / total_orgs * 100, 1) if total_orgs else 0
            ),
            'member_count': member_count,
            'orgs_without_member': total_orgs - member_count,
        },
        'by_position': [
            {'position': b, 'count': bucket_counts[b]}
            for b in POSITION_BUCKET_ORDER if b in bucket_counts
        ],
        'rows': rows,
        'include_contacts': include_contacts,
    }
