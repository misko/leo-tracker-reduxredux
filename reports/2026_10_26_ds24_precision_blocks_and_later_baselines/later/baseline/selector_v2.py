"""Pure owner selection matching the original accepted-owner panel rule.

Scores and eligibility are supplied by the unchanged RF calculation. This helper
does not calculate scores, load observations, or choose satellite identities.
The old frozen replay.py remains unchanged for provenance.
"""
import math


def nominate(families, owners):
    ranked = sorted(
        (f for f in families if f['has_eligible_owner']),
        key=lambda f: (-f['paired_score'], f['family']),
    )
    if not ranked:
        return None, None
    target = min(
        (o for o in owners if o['eligible'] and o['family'] == ranked[0]['family']),
        key=lambda o: (-o['paired_score'], o['owner']),
    )
    low = sorted(
        (f for f in ranked if f['family'] != target['family'] and f['paired_score'] > 0),
        key=lambda f: (f['paired_score'], f['family']),
    )[:max(1, math.ceil(len(ranked) / 4))]
    scores = {f['family']: f['paired_score'] for f in low}
    controls = sorted(
        (o for o in owners if o['eligible'] and o['family'] in scores),
        key=lambda o: (
            o['receiver'] == target['receiver'], scores[o['family']],
            o['paired_score'], o['owner'],
        ),
    )
    return target, controls[0] if controls else None
