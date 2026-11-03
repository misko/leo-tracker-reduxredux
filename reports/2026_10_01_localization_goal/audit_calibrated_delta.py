"""Compare local replacement with full scalar and vectorized reconstruction."""
import json
import time
from pathlib import Path

import numpy as np

from candidate_calibrated_cached_joint import CandidateJointObjective
from calibrated_proposal_delta import ProposalDelta
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent
profile_path = HERE/'calibrated-proposal-profile-v1.json'
assert digest(profile_path) == profile_path.with_suffix('.sha256').read_text().strip()
profile = json.loads(profile_path.read_text())
sources = dict(profile['source_sha256'])
for path in [Path(__file__), HERE/'calibrated_proposal_delta.py']:
    sources[str(path)] = digest(path)
verify_sources(sources)
verify_sources(profile['input_sha256'])
rows, setup = [], []
for unit in profile['units']:
    path = HERE/'calibrated-alternating-v1'/(unit+'-candidate.json')
    receipt = json.loads(path.read_text())
    model = CandidateJointObjective(unit, state=receipt['full_state'], assignments=receipt['assignments'])
    started = time.perf_counter()
    delta = ProposalDelta(model)
    setup.append(dict(unit=unit, seconds=time.perf_counter()-started))
    assert abs(delta.value-model.evaluate(model.initial, gradient=False)[0]) < 1e-7
    for item in [r for r in profile['rows'] if r['unit'] == unit]:
        track = item['track']
        port, old = model.base.ports[track], receipt['assignments'][track]
        scores = np.asarray(port.score_all(delta.state)).copy()
        scores[old] = -np.inf
        best = int(np.argmax(scores))
        started = time.perf_counter()
        value, clean, choices, gain = delta.score(track, best)
        fast_s = time.perf_counter()-started
        started = time.perf_counter()
        full = CandidateJointObjective(unit, state=clean, assignments=choices, context=model.base)
        train, additional = full.base.components(clean[:2])
        full_s = time.perf_counter()-started
        scalar = full.evaluate(full.initial, gradient=False)[0]
        error = max(abs(value-scalar), abs(value-(train-additional)))
        assert error < 1e-7
        unchanged, _, _, _ = delta.score(track, old)
        assert abs(unchanged-delta.value) < 1e-7
        rows.append(dict(unit=unit, track=track, difference=error, delta_s=fast_s,
            reconstruction_s=full_s, old_clutter=old == port.candidate_count,
            new_clutter=best == port.candidate_count, prior_gain=gain,
            old_identity_shared=receipt['assignments'].count(old) > 1))
assert len(rows) == profile['alternatives'] == 92
verify_sources(sources)
verify_sources(profile['input_sha256'])
result = dict(rows=rows, setup=setup, source_sha256=sources,
    input_sha256={str(profile_path): digest(profile_path), **profile['input_sha256']},
    alternatives=len(rows), maximum_difference=max(r['difference'] for r in rows),
    median_delta_s=float(np.median([r['delta_s'] for r in rows])),
    median_reconstruction_s=float(np.median([r['reconstruction_s'] for r in rows])),
    speedup_including_setup=sum(r['reconstruction_s'] for r in rows)/
        (sum(r['delta_s'] for r in rows)+sum(r['seconds'] for r in setup)),
    clutter_to_satellite=sum(r['old_clutter'] and not r['new_clutter'] for r in rows),
    satellite_to_clutter=sum(not r['old_clutter'] and r['new_clutter'] for r in rows),
    shared_old_identity=sum(r['old_identity_shared'] and not r['old_clutter'] for r in rows),
    nonzero_epoch_profiling=sum(r['prior_gain'] > 0 for r in rows),
    qualification='92fixed-state alternatives and92no-op checks at2failed endpoints. '
    'Failed fits remain failed; no geographic scoring or continuation. Timing includes '
    'delta-cache setup but excludes common initial scan/model preparation. Exact scores '
    'at fixed state only; rebuild cache after continuous moves or accepted assignments.')
output = HERE/'calibrated-delta-audit-v1.json'
with output.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
output.with_suffix('.sha256').write_text(digest(output)+'\n')
print(json.dumps({k: v for k, v in result.items() if k not in ['rows', 'source_sha256', 'input_sha256']}, indent=2))
