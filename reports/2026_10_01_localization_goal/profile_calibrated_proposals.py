"""Locate proposal cost at failed endpoints without fitting or geographic scoring."""
import json
import time
from pathlib import Path

import numpy as np

from candidate_calibrated_cached_joint import CandidateJointObjective
from regression_batch import digest, verify_sources
from leo.analysis.localization_epoch_profile import profile_unused_epochs

HERE = Path(__file__).resolve().parent
directory = HERE/'calibrated-alternating-v1'
freeze = directory/'sources.json'
assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
frozen = json.loads(freeze.read_text())
sources = dict(frozen['source_sha256'])
sources[str(Path(__file__))] = digest(__file__)
verify_sources(sources)
rows, parents = [], {}
for unit, arm in frozen['pairs']:
    if arm != 'candidate':
        continue
    path = directory/(unit+'-candidate.json')
    assert digest(path) == path.with_suffix('.sha256').read_text().strip()
    receipt = json.loads(path.read_text())
    if receipt['reason'] != 'wall_budget':
        continue
    parents[str(path)] = digest(path)
    state, choices = np.asarray(receipt['full_state']), receipt['assignments']
    model = CandidateJointObjective(unit, state=state, assignments=choices)
    verify_sources(receipt['inputs'])
    for track, (port, old) in enumerate(zip(model.base.ports, choices, strict=True)):
        scores = np.asarray(port.score_all(state)).copy()
        scores[old] = -np.inf
        best = int(np.argmax(scores))
        if not np.isfinite(scores[best]):
            continue
        assignments = list(choices)
        assignments[track] = best
        clean, _ = profile_unused_epochs(state, assignments, len(state)-5)
        start = time.perf_counter()
        proposal = CandidateJointObjective(unit, state=clean, assignments=assignments,
                                           context=model.base)
        construction = time.perf_counter()-start
        start = time.perf_counter()
        train, candidate = proposal.base.components(clean[:2])
        vector = time.perf_counter()-start
        start = time.perf_counter()
        scalar = proposal.evaluate(proposal.initial, gradient=False)[0]
        scalar_time = time.perf_counter()-start
        difference = abs(train-candidate-scalar)
        assert difference < 1e-7
        rows.append(dict(unit=unit, track=track, construction_s=construction,
            vector_s=vector, scalar_s=scalar_time, difference=difference))
verify_sources(sources)
verify_sources(parents)
result = dict(rows=rows, source_sha256=sources, input_sha256=parents,
    alternatives=len(rows), units=sorted({r['unit'] for r in rows}),
    median_construction_s=float(np.median([r['construction_s'] for r in rows])),
    median_vector_s=float(np.median([r['vector_s'] for r in rows])),
    median_scalar_s=float(np.median([r['scalar_s'] for r in rows])),
    construction_share_of_vector_path=sum(r['construction_s'] for r in rows)/
        sum(r['construction_s']+r['vector_s'] for r in rows),
    maximum_value_difference=max(r['difference'] for r in rows),
    qualification='Profiling at sealed failed endpoints only; not resumed fits or accepted results. '
    'Construction uses cached scan context but rebuilds all prediction slots. Timings exclude '
    'catalogue scoring and continuous optimization. Scalar measured after vector, no timing '
    'equivalence claim. No GPS or geographic scoring of failed states.')
path = HERE/'calibrated-proposal-profile-v1.json'
with path.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
path.with_suffix('.sha256').write_text(digest(path)+'\n')
print(json.dumps({k: v for k, v in result.items() if k not in ['rows', 'source_sha256', 'input_sha256']}, indent=2))
