"""ALGO06: additive causal family recovery over immutable ALGO05 results."""
import math
from leo.contracts.fast_graph_position import ARMS, KIND
from leo.contracts.fast_graph_position_v4 import validate_terminal as validate_previous, owners as previous_owners

MODEL_VERSION = 'algo06-causal-residual-family-v1'
NAMESPACE = 'fast-scan-graph-position-v5'
POLICIES = {'48h_15s': (48, 15, False), '72h_15s': (72, 15, False),
            '72h_30s': (72, 30, False), '72h_30s_recency': (72, 30, True)}
GATES = {'optimizer', 'phase', 'incumbent_exact_orbits', 'existing_owners_preserved',
         'family_residuals', 'phase_interior', 'quadrature'}

def owners(terminal):
    if terminal['decision'] == 'ALGO05_additive':
        return {a: dict(terminal['candidate']['trial']['arms'][a]['proposed_owners']) for a in ARMS}
    return previous_owners(terminal['incumbent'])

def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

def validate_terminal(doc, *, input_sha256):
    try:
        return _validate(doc, input_sha256)
    except (KeyError, TypeError, IndexError, OverflowError) as exc:
        raise ValueError('Malformed v5 terminal') from exc

def _validate(d, sha):
    if (d.get('schema_version') != 5 or d.get('kind') != KIND
        or d.get('model_version') != MODEL_VERSION or d.get('input_sha256') != sha
        or d.get('state') not in ('complete', 'failed', 'unavailable')):
        raise ValueError('Graph position v5 identity mismatch')
    if d['state'] != 'complete':
        if d.get('position') is not None:
            raise ValueError('Unqualified position')
        return d
    old = validate_previous(d['incumbent'], input_sha256=sha)
    if old['state'] != 'complete' or old['session_id'] != d['session_id']:
        raise ValueError('Wrong ALGO05 incumbent')
    if (d.get('reference_usage') != 'none' or d.get('future_TLE_used') is not False
        or d.get('matched_c_inputs') is not True or d.get('selected_arm') != 'fitted_c'
        or d.get('recovery_policy') not in POLICIES):
        raise ValueError('Contradictory inference provenance')
    times = [d[k] for k in ('incumbent_seconds', 'recovery_seconds', 'total_seconds')]
    if (any(not finite(t) or t < 0 for t in times) or times[0] != old['total_seconds']
        or times[1] > 1200 or times[2] > 6000 or abs(times[0]+times[1]-times[2]) > 1e-6):
        raise ValueError('Invalid runtime accounting')
    if d['decision'] == 'ALGO05_fallback':
        if d.get('candidate') is not None or d['position'] != old['position']:
            raise ValueError('Fallback must preserve exact ALGO05 position')
        return d
    if d['decision'] != 'ALGO06_additive' or (d.get('read_audit') or {}).get('verified') is not True:
        raise ValueError('Missing guarded recovery proof')
    c = d['candidate']; prior = owners(old)
    ids = c['target_ids']; universe = set(c['observation_ids']); norad = c['norad']
    if (not isinstance(norad, int) or isinstance(norad, bool) or norad <= 0
        or len(ids) < 20 or len(set(ids)) != len(ids) or not set(ids) <= universe
        or any(set(ids) & set(v) or norad in v.values() for v in prior.values())):
        raise ValueError('Recovery must add a native, previously unowned new family')
    stamps = c['target_times_s']
    if (len(stamps) != len(ids) or any(not finite(t) for t in stamps)
        or stamps[-1]-stamps[0] < 15 or any(not 0 < b-a <= 5 for a,b in zip(stamps,stamps[1:]))):
        raise ValueError('Invalid contiguous target times')
    age_limit, bound, _ = POLICIES[d['recovery_policy']]
    record = c['element']; cutoff = c['cutoff_utc_ns']
    if not isinstance(cutoff, int) or cutoff <= 0:
        raise ValueError('Explicit scan cutoff required')
    for key in ('element_epoch_utc_ns', 'collected_utc_ns'):
        if not isinstance(record[key], int) or not 0 <= cutoff-record[key] <= age_limit*3600*1e9:
            raise ValueError('Noncausal or over-age element')
    if c['screen']['policy'] != d['recovery_policy'] or c['screen']['screen_pass'] is not True:
        raise ValueError('Wrong screening policy')
    for arm in ARMS:
        folds = c['screen']['arms'][arm]['folds']
        if set(folds) != {'full', '20261031', '94721', '4081'}:
            raise ValueError('Three independent training partitions required')
        for fold in folds.values():
            if fold['winner']['norad'] != norad or not finite(fold['margin']) or fold['margin'] < 10:
                raise ValueError('Unstable or ambiguous satellite identity')
        replay = c['replay_checks'][arm]
        if any(not finite(replay[k]) or abs(replay[k]) > 1e-4 for k in
               ('incumbent_core_objective_difference', 'full_selected_likelihood_difference')):
            raise ValueError('Incumbent likelihood differs')
        for row in (c['control'][arm], c['trial']['arms'][arm]):
            if (set(row['checks']) != GATES or any(v is not True for v in row['checks'].values())
                or row['all_checked_gates_pass'] is not True or row['changed_incumbent_ids']
                or row['history'][-1]['success'] is not True
                or not finite(row['history'][-1]['phase_change_s'])
                or not 0 <= row['history'][-1]['phase_change_s'] <= .01
                or any(r['all_pass'] is not True for r in row['incumbent_exact_orbits'])
                or row['quadrature']['local_agreement'] is not True):
                raise ValueError('Candidate or control physical gates failed')
            for family in row['family_details']:
                if (not finite(family['phase_boundary_mass']) or not 0 <= family['phase_boundary_mass'] < .01
                    or any(g['compatible'] is not True for g in family['gates'])):
                    raise ValueError('Family compatibility failed')
            lat, lon = row['endpoint_latlon']
            if not finite(lat) or not finite(lon) or not -90<=lat<=90 or not -180<=lon<=180:
                raise ValueError('Invalid position')
        if c['trial']['entry']['observation_ids'] != ids or c['trial']['entry']['norad'] != norad:
            raise ValueError('Trial identity differs from screened source')
        if c['trial']['prior']['phase_limit_s'] != bound:
            raise ValueError('Different predictive phase bound')
        expected = dict(prior[arm], **dict.fromkeys(ids, norad))
        if c['published_owners'][arm] != expected or not set(expected) <= universe:
            raise ValueError('Published ownership is not an exact additive extension')
    expected = dict(zip(('latitude_deg','longitude_deg'), c['trial']['arms']['fitted_c']['endpoint_latlon']))
    if d['position'] != expected:
        raise ValueError('Position differs from selected fit')
    return d
