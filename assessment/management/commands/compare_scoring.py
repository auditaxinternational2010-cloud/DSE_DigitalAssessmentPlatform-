"""Read-only: show how the reporting rewrite changes every existing score.

The rewrite changed three things about how scores are produced:

  1. Overall score is a flat mean over criteria, not a mean of category means.
  2. Unanswered criteria are still excluded, but completeness is now reported.
  3. Informal-sector organisations are ranked in their own league.

Nothing about the stored data changed - there is no migration and no field was
added, removed or rewritten. But because reports are computed live on every
view, an organisation that already received a report will see a different
number after deploy. This command shows exactly which numbers move, and by how
much, so that is a decision rather than a surprise.

Writes nothing. Safe to run against production.

    python manage.py compare_scoring
    python manage.py compare_scoring --cycle 2026
    python manage.py compare_scoring --distributed-only
"""
from django.core.management.base import BaseCommand

from assessment.models import (
    AwardCycle, Response, VerifierResponse, categories_for_org,
)


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def _old_overall(questionnaire):
    """The pre-rewrite algorithm: mean of category means, numerics included."""
    categories = list(
        categories_for_org(questionnaire.cycle, questionnaire.organization)
        .prefetch_related('criteria')
    )
    verifier_scores = {}
    for vr in VerifierResponse.objects.filter(questionnaire=questionnaire):
        verifier_scores.setdefault(vr.criterion_id, []).append(vr.score)
    member = {
        r.criterion_id: r.score
        for r in Response.objects.filter(questionnaire=questionnaire)
    }

    cat_v, cat_m = [], []
    for cat in categories:
        crits = [c for c in cat.criteria.all() if c.is_active]
        cat_v.append(_avg([_avg(verifier_scores.get(c.id, [])) for c in crits]))
        cat_m.append(_avg([member.get(c.id) for c in crits]))
    return _avg(cat_v), _avg(cat_m)


class Command(BaseCommand):
    help = 'Compare pre- and post-rewrite report scores. Read-only.'

    def add_arguments(self, parser):
        parser.add_argument('--cycle', type=int, default=None,
                            help='Limit to one cycle year.')
        parser.add_argument('--distributed-only', action='store_true',
                            help='Only questionnaires already released to members.')

    def handle(self, *args, **options):
        from assessment.analytics import compute_cycle_analytics

        cycles = AwardCycle.objects.all().order_by('-year')
        if options['cycle']:
            cycles = cycles.filter(year=options['cycle'])

        if not cycles.exists():
            self.stdout.write(self.style.WARNING('No cycles found.'))
            return

        grand_moved = grand_total = grand_released = 0

        for cycle in cycles:
            questionnaires = cycle.questionnaires.filter(
                is_submitted=True).select_related('organization')
            if options['distributed_only']:
                questionnaires = questionnaires.filter(is_distributed=True)
            if not questionnaires.exists():
                continue

            self.stdout.write('')
            self.stdout.write(self.style.MIGRDSE_HEADING(
                f'=== {cycle.name} ({cycle.year}) ==='))

            analytics = compute_cycle_analytics(cycle)
            new_by_pk = {
                r['questionnaire'].pk: r
                for league in analytics['leagues']
                for r in league['ranked_orgs']
            }

            self.stdout.write(
                f'{"Organisation":<34}{"old":>7}{"new":>7}{"move":>8}'
                f'{"compl":>8}{"league":>10}  released'
            )
            self.stdout.write('-' * 88)

            moved = 0
            for q in questionnaires.order_by('organization__name'):
                old_v, _old_m = _old_overall(q)
                row = new_by_pk.get(q.pk)
                new_v = row['overall_verified_score'] if row else None
                compl = f"{row['completeness']:.0f}%" if row else '-'
                league = row['league'] if row else '-'

                if old_v is None and new_v is None:
                    delta = '   n/a'
                elif old_v is None or new_v is None:
                    delta = ' APPEARS' if old_v is None else ' DROPS'
                    moved += 1
                else:
                    d = round(new_v - old_v, 1)
                    delta = f'{d:+.1f}' if d else '   ='
                    if d:
                        moved += 1

                released = 'YES' if q.is_distributed else '-'
                if q.is_distributed:
                    grand_released += 1

                style = self.style.WARNING if delta.strip() not in ('=', 'n/a') else str
                self.stdout.write(style(
                    f'{q.organization.name[:33]:<34}'
                    f'{("-" if old_v is None else old_v):>7}'
                    f'{("-" if new_v is None else new_v):>7}'
                    f'{delta:>8}{compl:>8}{league:>10}  {released}'
                ))
                grand_total += 1

            grand_moved += moved

            leagues = ', '.join(
                f"{l['label']} ({l['ranked_count']} ranked)"
                for l in analytics['leagues'])
            self.stdout.write(f'  leagues: {leagues or "none"}')

        self.stdout.write('')
        self.stdout.write(self.style.MIGRDSE_HEADING('=== SUMMARY ==='))
        self.stdout.write(f'  questionnaires examined : {grand_total}')
        self.stdout.write(f'  scores that change      : {grand_moved}')
        self.stdout.write(f'  already released        : {grand_released}')
        if grand_released and grand_moved:
            self.stdout.write(self.style.WARNING(
                '  Some released reports will show different numbers after deploy.'))
        self.stdout.write(self.style.SUCCESS('  No data was modified.'))
