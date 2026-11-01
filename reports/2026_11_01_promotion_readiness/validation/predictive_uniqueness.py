"""Conditional finalist guard; no GPS, catalogue discovery, or probabilities.

The zero threshold is a conservative ordering control, not a calibrated
statistical significance threshold. More than five folds may share training
data; unique held sets are not independently replicated experiments.
"""
import math

ARMS = ('c0', 'fitted_c')


def conditional_uniqueness(rows, partitions, candidates, proposed, *,
                           model='receiver_offset', phase_sd_s=5.,
                           minimum_unique_folds=5, minimum_margin=0.):
    """Require proposed to beat EVERY matched nominee on EVERY unique fold.

    rows: arm, fold, norad, model, phase_sd_s, predictive_score.
    partitions: fold, held_blocks (synchronized whole-group assignments).
    Lower normalized predictive scores win. Missing fits and too few unique
    partitions are `not_evaluated`; an observed nonpositive margin is `rejected`.
    Candidates must be the complete common finalist universe, including the
    incumbent, not only hypotheses that passed a preceding predictive screen.
    """
    candidates = sorted(set(map(int, candidates)))
    proposed = int(proposed)
    if proposed not in candidates or len(candidates) < 2:
        raise ValueError('proposed and at least one competitor must be present')
    if minimum_unique_folds < 1 or not math.isfinite(minimum_margin):
        raise ValueError('finite threshold and positive fold requirement needed')
    unique = {}
    for part in partitions:
        signature = tuple(sorted(map(int, part['held_blocks'])))
        if not signature:
            raise ValueError('empty held partition')
        unique.setdefault(signature, int(part['fold']))
    folds = list(unique.values())
    selected = [r for r in rows if r['model'] == model and float(r['phase_sd_s']) == phase_sd_s]
    lookup = {}
    for r in selected:
        key = (r['arm'], int(r['fold']), int(r['norad']))
        if key in lookup:
            raise ValueError('duplicate model/candidate/fold fit')
        score = float(r['predictive_score'])
        if not math.isfinite(score):
            raise ValueError('finite normalized predictive score required')
        lookup[key] = score
    missing = [dict(arm=a, fold=f, norad=n) for a in ARMS for f in folds for n in candidates
               if (a,f,n) not in lookup]
    report = dict(proposed=proposed, candidates=candidates, model=model,
                  phase_sd_s=phase_sd_s, minimum_unique_folds=minimum_unique_folds,
                  required_minimum_margin_exclusive=minimum_margin,
                  unique_folds=len(folds), total_partitions=len(partitions),
                  retained_fold_ids=folds, missing=missing, competitors=[],
                  scope='Conditional on supplied full-data finalist inventory, graph/alias choices, and cavity calibration; not independent discovery or an identity probability')
    if missing or len(folds) < minimum_unique_folds:
        return dict(report, status='not_evaluated', passed=False,
                    reason='missing_matched_fits' if missing else 'insufficient_unique_partitions', minimum_margin=None)
    for a in ARMS:
        for n in candidates:
            if n == proposed:
                continue
            margins = [lookup[(a,f,n)] - lookup[(a,f,proposed)] for f in folds]
            report['competitors'].append(dict(arm=a,norad=n,margins=margins,
                minimum_margin=min(margins), mean_margin=sum(margins)/len(margins),
                wins=sum(m > minimum_margin for m in margins), folds=len(margins)))
    observed = min(r['minimum_margin'] for r in report['competitors'])
    passed = observed > minimum_margin
    return dict(report,status='passed' if passed else 'rejected',passed=passed,
                reason=None if passed else 'nonpositive_or_subthreshold_competitor_margin',minimum_margin=observed)


def from_saved_screen(screen, proposed, **thresholds):
    """Audit existing per-track-offset screen; receiver-shared fits are absent.

    This adapter deliberately labels the inherited discrepancy model. Call
    conditional_uniqueness with model='receiver_offset' for that stronger
    requirement; passing this legacy adapter does not satisfy that requirement.
    """
    rows = [dict(arm=f['arm'],fold=f['fold'],norad=int(n),model='track_offset',phase_sd_s=5.,
                 predictive_score=r['predictive_score'])
            for f in screen.get('folds',[]) for n,r in f['fits'].items()]
    out = conditional_uniqueness(rows, screen.get('partitions',[]), screen['nominees'], proposed,
                                model='track_offset', **thresholds)
    out['receiver_shared_evidence'] = 'not_evaluated: absent from saved screen schema'
    return out


def from_additional_checks(checks, **thresholds):
    return conditional_uniqueness(checks['rows'],checks['parts'],checks['provenance'],checks['new'],**thresholds)
