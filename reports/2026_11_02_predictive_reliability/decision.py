"""Predeclared conditional predictive decision; never uses geography."""
import math

ARMS = ('c0', 'fitted_c')
SCALES = (1.0, 4.0)
TOLERANCE = 1e-4


def score(row, subset):
    value = row['scores'][subset]
    if value['status'] != 'complete':
        raise ValueError('No held observations for ' + subset)
    bounded = value['bounded']
    cost = float(bounded['negative_twice_log_density'])
    uncertainty = 2 * sum(float(bounded[key]['relative_quadrature_error'])
                          for key in ('prior_box', 'posterior_box'))
    if not math.isfinite(cost) or not math.isfinite(uncertainty):
        raise ValueError('Nonfinite predictive score or integration error')
    return cost, uncertainty


def decide(plans, rows):
    """Require all five planned comparisons; failed cells cannot vote."""
    reasons, comparisons = [], []
    index = {}
    for row in rows:
        key = (row['split'], row['arm'], float(row['SD_scale']))
        if key in index:
            raise ValueError('Duplicate predictive cell')
        index[key] = row
    if len(plans) != 5 or sum(p['kind'] == 'time_group' for p in plans) != 3:
        reasons.append('incomplete_partition_roster')
    for plan in plans:
        name = plan['name']
        if not plan['eligible']:
            reasons.append(name + ':unsupported_transfer_or_time_split')
        matching = [index.get((name, arm, sd)) for arm in ARMS for sd in SCALES]
        if any(r is None for r in matching):
            reasons.append(name + ':missing_cells')
            continue
        if any(r.get('status') != 'complete' for r in matching):
            reasons.append(name + ':incomplete_fit')
            continue
        if len({(r['train_ids_sha256'], r['held_ids_sha256']) for r in matching}) != 1:
            reasons.append(name + ':unmatched_native_partitions')
            continue
        qualified = plan['eligible'] and all(r.get('numerical_fit_qualified') for r in matching)
        if not qualified:
            reasons.append(name + ':paired_model_qualification_failed')
        for arm in ARMS:
            before, after = [index[(name, arm, sd)] for sd in SCALES]
            try:
                a, ae = score(before, 'all'); b, be = score(after, 'all')
                other_gain, other_tol = None, None
                if plan['kind'] == 'time_group':
                    oa, oae = score(before, 'other'); ob, obe = score(after, 'other')
                    other_gain, other_tol = oa-ob, max(TOLERANCE, oae+obe)
                comparisons.append(dict(split=name, kind=plan['kind'], arm=arm,
                    paired_qualified=qualified, gain_SD4=a-b,
                    numerical_tolerance=max(TOLERANCE, ae+be),
                    other_family_gain_SD4=other_gain, other_family_tolerance=other_tol))
            except (KeyError, ValueError) as exc:
                reasons.append(name + ':' + arm + ':' + str(exc))
    verdict = 'inconclusive'
    if not reasons and len(comparisons) == 10:
        def favors(sign):
            return all(sign*r['gain_SD4'] > r['numerical_tolerance']
                and (r['other_family_gain_SD4'] is None or
                     sign*r['other_family_gain_SD4'] >= -r['other_family_tolerance'])
                for r in comparisons)
        if favors(1):
            verdict = 'SD4_conditionally_favored'
        elif favors(-1):
            verdict = 'SD1_conditionally_favored'
        else:
            reasons.append('cross_partition_or_arm_disagreement_tie_or_other_family_harm')
    return dict(verdict=verdict, reasons=sorted(set(reasons)), comparisons=comparisons,
                qualified_partitions=sum(all(r['paired_qualified'] for r in comparisons if r['split']==p['name'])
                    and sum(r['split']==p['name'] for r in comparisons)==2 for p in plans),
                scope='Conditional RF challenge-panel diagnostic; not calibrated probability or production acceptance')
