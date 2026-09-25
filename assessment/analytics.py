"""Report analytics — the numbers behind every report in the system.

Two words matter here and they are NOT interchangeable:

  verified  The judges' score. This is THE score. It sets the rank and the
            award. Where a criterion was scored by several judges it is the
            mean of their scores, and the individual scores are kept alongside
            it so a report can show who said what and why.

  claimed   The organisation's own self-assessment. Not a score — a claim made
            before anyone checked. Its only value is diagnostic: the distance
            between claimed and verified measures how well an organisation
            knows itself, which is why that distance is reported in words
            ("over-stated by 0.6") rather than as a bare signed number.

Overall scores are a FLAT MEAN OVER CRITERIA, never a mean of category means,
so a 3-criterion category cannot outweigh a 20-criterion one.

Unanswered criteria are excluded from the mean and reported separately as
`completeness`. They are never silently averaged away: an organisation that
answered 8 of 21 criteria well must not quietly outrank one that answered all
21 honestly, so every ranking carries its completeness beside it.

Informal-sector organisations answer a different category set from everyone
else, so they are ranked in their own league. Comparing the two is not a
like-for-like comparison and the code refuses to pretend otherwise.

Models are imported inside functions, matching coverage.py.
"""

# A criterion at or above this verified level is reported as a strength.
STRENGTH_LEVEL = 4

# Below this, a criterion is treated as a live improvement priority.
PRIORITY_LEVEL = 3

# Claimed-vs-verified differences smaller than this are noise, not over-claiming.
GAP_TOLERANCE = 0.25

# How many criteria the strengths / priorities lists carry.
HIGHLIGHT_LIMIT = 6

MAX_LEVEL = 5


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def _weighted_avg(pairs):
    pairs = [(v, w) for v, w in pairs if v is not None and w and float(w) > 0]
    if not pairs:
        return None
    total_weight = sum(float(w) for _, w in pairs)
    return round(sum(float(v) * float(w) for v, w in pairs) / total_weight, 1)


def _pct(part, whole):
    return round(part / whole * 100, 1) if whole else 0.0


def _gap(verified, claimed):
    """Verified minus claimed, or None if either side is missing."""
    if verified is None or claimed is None:
        return None
    return round(verified - claimed, 1)


def _gap_words(gap):
    """Say what the gap MEANS, so no reader has to decode a signed number.

    Returns (direction, phrase). Direction is a stable token for styling;
    the phrase is what a reader actually sees.
    """
    if gap is None:
        return 'none', ''
    if abs(gap) < GAP_TOLERANCE:
        return 'match', 'Self-assessment matched the verified result'
    if gap < 0:
        return 'over', f'Self-assessment was {abs(gap)} higher than verified'
    return 'under', f'Self-assessment was {gap} lower than verified'


def _rank_within(pairs):
    """Rank (key, score) pairs highest-first. Equal scores share a rank.

    Returns {key: rank}. Entries with a None score are unranked and absent,
    because an unscored organisation has no position, not last position.
    """
    scored = sorted(
        [(k, s) for k, s in pairs if s is not None],
        key=lambda kv: -kv[1],
    )
    ranks = {}
    previous_score = None
    previous_rank = 0
    for index, (key, score) in enumerate(scored, 1):
        if score == previous_score:
            ranks[key] = previous_rank
        else:
            ranks[key] = index
            previous_rank = index
            previous_score = score
    return ranks


# ── Single organisation ──────────────────────────────────────────────────────

def compute_org_analytics(questionnaire, *, benchmark=None):
    """Everything one organisation's report needs, in one pass.

    `benchmark` is the optional cohort context from `compute_org_benchmark`.
    It carries only aggregates and this organisation's own positions — never
    another organisation's name or score — because members read this report.
    """
    from .models import (
        EvidenceLink, LevelIndicator, Response, VerifierResponse, JudgeResponse,
        categories_for_org,
    )

    categories = list(
        categories_for_org(questionnaire.cycle, questionnaire.organization, questionnaire=questionnaire)
        .prefetch_related('criteria')
    )
    criteria_by_cat = {
        cat.id: sorted(
            [c for c in cat.criteria.all() if c.is_active],
            key=lambda c: c.number,
        )
        for cat in categories
    }
    all_criteria = [c for crits in criteria_by_cat.values() for c in crits]
    criterion_ids = [c.id for c in all_criteria]

    member_map = {
        r.criterion_id: r
        for r in Response.objects.filter(questionnaire=questionnaire)
    }

    # Judge scores are the official score. Each judge has an independent row;
    # the average is calculated only from submitted judge scores.
    judge_rows = {}
    for jr in (JudgeResponse.objects
               .filter(questionnaire=questionnaire)
               .select_related('judge')
               .order_by('judge__first_name', 'judge__username')):
        judge_rows.setdefault(jr.criterion_id, []).append(jr)

    secretariat_rows = {}
    for sr in (VerifierResponse.objects
               .filter(questionnaire=questionnaire)
               .select_related('verifier')
               .order_by('verifier__first_name', 'verifier__username')):
        secretariat_rows.setdefault(sr.criterion_id, []).append(sr)

    # (criterion_id, level) -> indicator text. This is what turns a bare "2"
    # into "you are at 2 because ...", and "3" into "to reach 3 you need ...".
    level_text = {
        (li.criterion_id, li.level): li.indicator
        for li in LevelIndicator.objects.filter(criterion_id__in=criterion_ids)
    }

    evidence_by_criterion = {}
    for link in (EvidenceLink.objects
                 .filter(response__questionnaire=questionnaire)
                 .select_related('document', 'response')):
        evidence_by_criterion.setdefault(
            link.response.criterion_id, []).append(link.document)

    bench_criteria = (benchmark or {}).get('criterion_avgs', {})
    bench_categories = (benchmark or {}).get('category_avgs', {})

    cat_entries = []
    every_entry = []

    for cat in categories:
        crit_entries = []

        for c in criteria_by_cat[cat.id]:
            member = member_map.get(c.id)
            use_judges = questionnaire.organization.requires_judging
            rows = judge_rows.get(c.id, []) if use_judges else secretariat_rows.get(c.id, [])
            scored_rows = [r for r in rows if r.score is not None]
            verified = _avg([r.score for r in scored_rows])

            # Every verifier who left a score or a comment, named. A report
            # that says "the verifier scored you 2" without saying which
            # verifier or why is the gap this whole module exists to close.
            verifier_entries = [
                {
                    'name': (r.judge.get_full_name() or r.judge.username) if use_judges else (r.verifier.get_full_name() or r.verifier.username),
                    'score': r.score,
                    'notes': (r.notes or '').strip(),
                }
                for r in rows
                if r.score is not None or (r.notes or '').strip()
            ]
            verifier_notes = [v for v in verifier_entries if v['notes']]

            scores = [r.score for r in scored_rows]
            spread = max(scores) - min(scores) if len(scores) > 1 else None

            # Floor, not round: a 3.5 mean means level 3 is demonstrated and
            # level 4 is not. Reporting it as 4 would credit unearned ground.
            level_now = int(verified) if verified is not None else None
            level_next = (
                level_now + 1
                if level_now is not None and level_now < MAX_LEVEL
                else None
            )

            claimed = None
            gap = _gap(verified, claimed)
            direction, phrase = _gap_words(gap)
            cohort = bench_criteria.get(c.id)

            entry = {
                'criterion': c,
                'category': cat,

                'claimed_score': claimed,
                'claimed_notes': member.response if member else '',
                'claimed_numeric_data': member.numeric_data if member else None,

                'verified_score': verified,
                'verifier_entries': verifier_entries,
                'verifier_notes': verifier_notes,
                'verifier_count': len(scored_rows),
                'judge_entries': verifier_entries,
                'judge_notes': verifier_notes,
                'judge_count': len(scored_rows),
                'spread': spread,
                # Two judges two levels apart is not a rounding difference,
                # it is a disagreement someone should look at before award.
                'is_disputed': spread is not None and spread >= 2,

                'gap': gap,
                'gap_direction': direction,
                'gap_phrase': phrase,

                'level_now': level_now,
                'level_now_text': level_text.get((c.id, level_now)) if level_now is not None else None,
                'level_next': level_next,
                'level_next_text': level_text.get((c.id, level_next)) if level_next is not None else None,

                'evidence': evidence_by_criterion.get(c.id, []),

                'cohort_avg': cohort,
                'vs_cohort': (
                    round(verified - cohort, 1)
                    if verified is not None and cohort is not None else None
                ),

                'is_numeric': c.is_numeric,
                'is_answered': bool(member and (member.response or '').strip()),
                'is_verified': verified is not None,
                'headroom': round(MAX_LEVEL - verified, 1) if verified is not None else None,

                # Back-compat with the pre-rewrite template/export vocabulary.
                'member_score': claimed,
                'member_notes': member.notes if member else '',
                'member_numeric_data': member.numeric_data if member else None,
                'verifier_score': verified,
            }
            crit_entries.append(entry)
            every_entry.append(entry)

        scorable = [e for e in crit_entries if not e['is_numeric']]
        verified_avg = _weighted_avg([(e['verified_score'], e['criterion'].weight) for e in scorable])
        claimed_avg = None
        cat_gap = _gap(verified_avg, claimed_avg)
        cat_direction, cat_phrase = _gap_words(cat_gap)
        cat_cohort = bench_categories.get(cat.id)

        cat_entries.append({
            'category': cat,
            'criteria': crit_entries,

            'verified_avg': verified_avg,
            'claimed_avg': claimed_avg,
            'gap': cat_gap,
            'gap_direction': cat_direction,
            'gap_phrase': cat_phrase,

            'answered': sum(1 for e in crit_entries if e['is_answered']),
            'total': len(crit_entries),
            'completeness': _pct(
                sum(1 for e in crit_entries if e['is_answered']), len(crit_entries)
            ),

            'cohort_avg': cat_cohort,
            'vs_cohort': (
                round(verified_avg - cat_cohort, 1)
                if verified_avg is not None and cat_cohort is not None else None
            ),
            'rank': (benchmark or {}).get('category_ranks', {}).get(cat.id),
            'rank_of': (
                (benchmark or {}).get('category_rank_totals', {}).get(cat.id)
                or (benchmark or {}).get('league_size')
            ),

            # Back-compat.
            'member_avg': claimed_avg,
            'verifier_avg': verified_avg,
        })

    # The workbook's parameter weights drive the final score.
    scorable_entries = [e for e in every_entry if not e['is_numeric']]
    overall_verified = _weighted_avg([(e['verified_score'], e['criterion'].weight) for e in scorable_entries])
    overall_claimed = None
    overall_gap = _gap(overall_verified, overall_claimed)
    overall_direction, overall_phrase = _gap_words(overall_gap)

    answered = sum(1 for e in every_entry if e['is_answered'])
    verified_count = sum(1 for e in scorable_entries if e['is_verified'])

    ranked = sorted(
        [e for e in scorable_entries if e['is_verified']],
        key=lambda e: e['verified_score'],
    )
    priorities = [e for e in ranked if e['verified_score'] < PRIORITY_LEVEL]
    if not priorities:
        # Everything already meets the bar; still show where the most ground
        # remains, so a strong organisation gets a next step rather than none.
        priorities = ranked[:HIGHLIGHT_LIMIT]
    strengths = [
        e for e in reversed(ranked) if e['verified_score'] >= STRENGTH_LEVEL
    ]

    disputed = [e for e in scorable_entries if e['is_disputed']]

    scored_cats = [e for e in cat_entries if e['verified_avg'] is not None]

    # The criterion-detail accordion opens here on load, so the section most
    # worth reading is on screen rather than merely reachable.
    for entry in cat_entries:
        entry['is_weakest'] = False
    if scored_cats:
        min(scored_cats, key=lambda e: e['verified_avg'])['is_weakest'] = True

    return {
        'overall_verified_score': overall_verified,
        'overall_claimed_score': overall_claimed,
        'overall_gap': overall_gap,
        'gap_direction': overall_direction,
        'gap_phrase': overall_phrase,

        'answered_count': answered,
        'criteria_count': len(every_entry),
        'completeness': _pct(answered, len(every_entry)),
        'verified_count': verified_count,
        'scorable_count': len(scorable_entries),
        'verification_completeness': _pct(verified_count, len(scorable_entries)),

        'categories': cat_entries,
        'priority_criteria': priorities[:HIGHLIGHT_LIMIT],
        'strength_criteria': strengths[:HIGHLIGHT_LIMIT],
        'disputed_criteria': disputed,

        'benchmark': benchmark,

        # Back-compat with the pre-rewrite templates and Excel/PDF exports.
        'overall_verifier_score': overall_verified,
        'overall_member_score': overall_claimed,
        'strengths': sorted(
            scored_cats, key=lambda e: e['verified_avg'], reverse=True)[:3],
        'weaknesses': sorted(scored_cats, key=lambda e: e['verified_avg'])[:3],
    }


def compute_org_benchmark(questionnaire):
    """This organisation's cohort context, with no other organisation exposed.

    Members read the org report, so this deliberately returns averages and
    this organisation's own positions only. Names and scores of peers stay in
    `compute_cycle_analytics`, which is admin/verifier-facing.
    """
    cycle_analytics = compute_cycle_analytics(questionnaire.cycle)
    league_key = questionnaire.organization.assessment_profile or (
        'informal' if questionnaire.organization.org_type == 'informal_sector' else 'main'
    )
    league = next((l for l in cycle_analytics['leagues'] if l['key'] == league_key), None)
    if not league:
        return None

    row = next(
        (r for r in league['ranked_orgs']
         if r['questionnaire'].pk == questionnaire.pk),
        None,
    )
    return {
        'league_key': league_key,
        'league_label': league['label'],
        # Ranked, not submitted: an organisation with no verified score holds
        # no position, so counting it in the denominator would overstate where
        # everyone else stands.
        'league_size': league['ranked_count'],
        'submitted_count': league['count'],
        'cohort_avg': league['avg'],
        'cohort_high': league['high'],
        'cohort_low': league['low'],
        'rank': row['rank'] if row else None,
        'criterion_avgs': league['criterion_avgs'],
        'category_avgs': league['category_avgs'],
        'category_ranks': (row or {}).get('category_ranks', {}),
        'category_rank_totals': league['category_rank_totals'],
    }


# ── Whole cycle ──────────────────────────────────────────────────────────────

def _build_league(key, label, questionnaires, criteria_by_cat,
                  member_map, judge_map, secretariat_map):
    """Rank one set of like-for-like organisations against each other."""
    category_ids = list(criteria_by_cat.keys())
    scorable_by_cat = {
        cat_id: [c for c in crits if not c.is_numeric]
        for cat_id, crits in criteria_by_cat.items()
    }
    all_scorable = [c for crits in scorable_by_cat.values() for c in crits]

    rows = []
    # criterion_id -> every verified score across the league, for the cohort mean
    criterion_pool = {}
    category_pool = {}

    for q in questionnaires:
        q_member = member_map.get(q.pk, {})
        q_judges = judge_map.get(q.pk, {}) if q.organization.requires_judging else secretariat_map.get(q.pk, {})

        verified_by_crit = {}
        for c in all_scorable:
            score = _avg(q_judges.get(c.id, []))
            verified_by_crit[c.id] = score
            if score is not None:
                criterion_pool.setdefault(c.id, []).append(score)

        cat_scores = {}
        for cat_id, crits in scorable_by_cat.items():
            cat_score = _weighted_avg([(verified_by_crit.get(c.id), c.weight) for c in crits])
            cat_scores[cat_id] = cat_score
            if cat_score is not None:
                category_pool.setdefault(cat_id, []).append(cat_score)

        # Flat over criteria, not a mean of the category means above.
        overall_verified = _weighted_avg(
            [(verified_by_crit.get(c.id), c.weight) for c in all_scorable])
        overall_claimed = None
        gap = _gap(overall_verified, overall_claimed)
        direction, phrase = _gap_words(gap)

        answered = sum(
            1 for crits in criteria_by_cat.values() for c in crits
            if c.id in q_member and (q_member[c.id].response or '').strip()
        )
        total = sum(len(crits) for crits in criteria_by_cat.values())

        rows.append({
            'questionnaire': q,
            'org': q.organization,
            'overall_verified_score': overall_verified,
            'overall_claimed_score': overall_claimed,
            'overall_gap': gap,
            'gap_direction': direction,
            'gap_phrase': phrase,
            'answered': answered,
            'total': total,
            'completeness': _pct(answered, total),
            'cat_scores': cat_scores,
            'league': key,
            # Back-compat.
            'overall_verifier_score': overall_verified,
            'overall_member_score': overall_claimed,
        })

    overall_ranks = _rank_within(
        [(r['questionnaire'].pk, r['overall_verified_score']) for r in rows])
    category_ranks = {
        cat_id: _rank_within(
            [(r['questionnaire'].pk, r['cat_scores'].get(cat_id)) for r in rows])
        for cat_id in category_ids
    }

    for r in rows:
        pk = r['questionnaire'].pk
        r['rank'] = overall_ranks.get(pk)
        r['category_ranks'] = {
            cat_id: category_ranks[cat_id].get(pk) for cat_id in category_ids
        }

    # Denominators count only organisations that actually hold a position.
    # "3 of 9" when three of the nine were never scored is a false statement
    # about where an organisation stands.
    ranked_count = len(overall_ranks)
    category_rank_totals = {
        cat_id: len(category_ranks[cat_id]) for cat_id in category_ids
    }

    # Unranked organisations sort last; they have no position, not last place.
    rows.sort(key=lambda r: (
        r['overall_verified_score'] is None,
        -(r['overall_verified_score'] or 0),
        r['org'].name,
    ))

    scores = [r['overall_verified_score'] for r in rows
              if r['overall_verified_score'] is not None]

    return {
        'key': key,
        'label': label,
        'ranked_orgs': rows,
        'count': len(rows),
        'ranked_count': ranked_count,
        'category_rank_totals': category_rank_totals,
        'avg': _avg(scores),
        'high': max(scores) if scores else None,
        'low': min(scores) if scores else None,
        'criterion_avgs': {
            cid: _avg(vals) for cid, vals in criterion_pool.items()},
        'category_avgs': {
            cat_id: _avg(vals) for cat_id, vals in category_pool.items()},
        'categories': [
            cat for cat in criteria_by_cat.keys()
        ],
    }


def compute_cycle_analytics(cycle):
    """Rankings for a whole cycle, split into like-for-like leagues."""
    from .models import Response, VerifierResponse, JudgeResponse
    from accounts.models import Organization

    questionnaires = list(
        cycle.questionnaires
        .filter(is_submitted=True)
        .select_related('organization', 'template')
        .order_by('organization__name')
    )

    all_categories = list(
        cycle.categories
        .filter(is_active=True)
        .prefetch_related('criteria')
        .order_by('order')
    )
    criteria_by_cat = {
        cat.id: [c for c in cat.criteria.all() if c.is_active]
        for cat in all_categories
    }
    cat_by_id = {cat.id: cat for cat in all_categories}

    if not questionnaires:
        return {
            'leagues': [],
            'category_table': [],
            'ranked_orgs': [],
            'cycle_avg_verifier': None,
            'cycle_high': None,
            'cycle_low': None,
            'category_leaders': [],
        }

    q_ids = [q.pk for q in questionnaires]

    member_map = {}
    for r in Response.objects.filter(questionnaire_id__in=q_ids):
        member_map.setdefault(r.questionnaire_id, {})[r.criterion_id] = r

    judge_map = {}
    for jr in JudgeResponse.objects.filter(
            questionnaire_id__in=q_ids, score__isnull=False):
        judge_map.setdefault(jr.questionnaire_id, {}).setdefault(
            jr.criterion_id, []).append(jr.score)

    secretariat_map = {}
    for sr in VerifierResponse.objects.filter(
            questionnaire_id__in=q_ids, score__isnull=False):
        secretariat_map.setdefault(sr.questionnaire_id, {}).setdefault(
            sr.criterion_id, []).append(sr.score)

    # A reusable template defines the comparison cohort. Organizations are
    # ranked only against others assigned to the same template. Legacy
    # questionnaires without a template retain profile-based grouping.
    profile_qs = {}
    for q in questionnaires:
        key = f'template:{q.template_id}' if q.template_id else (
            q.organization.assessment_profile or
            ('informal' if q.organization.org_type == 'informal_sector' else 'main')
        )
        profile_qs.setdefault(key, []).append(q)

    profile_labels = dict(Organization.ASSESSMENT_PROFILE_CHOICES)

    leagues = []
    for key, qs in profile_qs.items():
        if key.startswith('template:'):
            template = qs[0].template
            cat_ids = {cat.id for cat in all_categories if cat.template_id == template.pk}
            label = template.name
        else:
            cat_ids = {
                cat.id for cat in all_categories
                if cat.template_id is None and (cat.assessment_profile or key) == key
            }
            label = profile_labels.get(key, key.replace('_', ' ').title())
        if not cat_ids:
            continue
        league = _build_league(
            key, label, qs,
            {cid: criteria_by_cat[cid] for cid in cat_ids},
            member_map, judge_map, secretariat_map,
        )
        league['category_objects'] = [
            cat_by_id[cid] for cid in cat_ids if cid in cat_by_id]
        league['category_objects'].sort(key=lambda c: (c.order, c.name))
        leagues.append(league)

    # Every organisation's standing in every category, not just best and worst.
    category_table = []
    for league in leagues:
        for cat in league['category_objects']:
            placings = sorted(
                [
                    {
                        'org': r['org'],
                        'questionnaire': r['questionnaire'],
                        'score': r['cat_scores'].get(cat.id),
                        'rank': r['category_ranks'].get(cat.id),
                    }
                    for r in league['ranked_orgs']
                    if r['cat_scores'].get(cat.id) is not None
                ],
                key=lambda p: p['rank'],
            )
            if placings:
                category_table.append({
                    'category': cat,
                    'league': league['key'],
                    'league_label': league['label'],
                    'placings': placings,
                    'avg': league['category_avgs'].get(cat.id),
                })

    ranked_orgs = [r for league in leagues for r in league['ranked_orgs']]
    all_scores = [r['overall_verified_score'] for r in ranked_orgs
                  if r['overall_verified_score'] is not None]

    category_leaders = [
        {
            'category': entry['category'],
            'league': entry['league'],
            'best_org': entry['placings'][0]['org'],
            'best_score': entry['placings'][0]['score'],
            'worst_org': entry['placings'][-1]['org'],
            'worst_score': entry['placings'][-1]['score'],
        }
        for entry in category_table
    ]

    return {
        'leagues': leagues,
        'category_table': category_table,
        'ranked_orgs': ranked_orgs,
        'cycle_avg_verifier': _avg(all_scores),
        'cycle_high': max(all_scores) if all_scores else None,
        'cycle_low': min(all_scores) if all_scores else None,
        'category_leaders': category_leaders,
    }
