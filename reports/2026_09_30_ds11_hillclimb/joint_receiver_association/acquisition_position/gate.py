"""Cohort-separated accuracy gate; missing or unqualified fits cannot pass."""
import numpy as np


def compare(reference, candidate):
    reference, candidate = np.asarray(reference, float), np.asarray(candidate, float)
    if reference.shape != candidate.shape or reference.ndim != 1 or not len(reference) or not np.isfinite(reference).all() or not np.isfinite(candidate).all():
        return dict(passed=False, complete=False)
    rmedian, cmedian = float(np.median(reference)), float(np.median(candidate))
    rp90, cp90 = float(np.quantile(reference, .9)), float(np.quantile(candidate, .9))
    wins = int(np.sum(candidate < reference))
    return dict(passed=bool(cmedian <= .95 * rmedian and cp90 <= rp90 and wins > len(reference) / 2), complete=True, reference_median_m=rmedian, signed_median_m=cmedian, reference_p90_m=rp90, signed_p90_m=cp90, wins=wins, count=len(reference))


def evaluate(rows):
    result = {}
    for cohort in ('original', 'additional'):
        group = [r for r in rows if r['cohort'] == cohort]
        qualified = bool(group) and all(r['doppler']['qualified'] and r['signed']['qualified'] for r in group)
        comparisons = {arm: compare([r[arm].get('distance_m', float('nan')) for r in group], [r['signed'].get('distance_m', float('nan')) for r in group]) for arm in ('original', 'doppler')}
        result[cohort] = dict(qualified=qualified, comparisons=comparisons, passed=qualified and all(r['passed'] for r in comparisons.values()))
    return dict(cohorts=result, passed=all(r['passed'] for r in result.values()))
