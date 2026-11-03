"""Reference-blind paired objective/gradient and construction-time comparison."""
import json
import time
from pathlib import Path

import numpy as np
from candidate_cached_joint import CandidateJointObjective as Cached
from candidate_joint_expansion_adapter import CandidateJointObjective as OriginalParent
from candidate_reassociation_joint import CandidateJointObjective as Original
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    freeze = HERE/'alternating-candidate-v1/sources.json'
    assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
    sources = json.loads(freeze.read_text())['source_sha256']
    for name in ['candidate_cached_joint.py', 'candidate_cached_spatial.py',
                 'audit_cached_candidate.py']:
        path = HERE/name
        sources[str(path)] = digest(path)
    verify_sources(sources)
    audit_path = HERE/'candidate-reassociation-audit-v1.json'
    assert digest(audit_path) == audit_path.with_suffix('.sha256').read_text().strip()
    rows = []
    for entry in json.loads(audit_path.read_text())['rows']:
        unit = entry['unit']
        path = HERE/'candidate-joint-expansion-v1'/(unit+'-candidate.json')
        assert digest(path) == path.with_suffix('.sha256').read_text().strip()
        receipt = json.loads(path.read_text())
        parent = OriginalParent(unit)
        context = parent.base
        original_initial = context.initial.copy()
        original_assignments = context.assignments.copy()
        original_slots = [list(s) for s in context.group_slots]
        state = context.initial.copy()
        state[parent.columns] = receipt['mean']
        cases = [('unchanged', receipt['assignments'])]
        for proposal in entry['proposals']:
            choices = receipt['assignments'].copy()
            choices[proposal['track_index']] = proposal['best_index']
            cases.append(('track-'+str(proposal['track_index']), choices))
        for label, choices in cases:
            models, durations = {}, {}
            order = ['original', 'cached'] if len(rows) % 2 == 0 else ['cached', 'original']
            for name in order:
                started = time.monotonic()
                if name == 'original':
                    models[name] = Original(unit, state=state, assignments=choices)
                else:
                    models[name] = Cached(unit, state=state, assignments=choices, context=context)
                durations[name] = time.monotonic()-started
            a, b = models['original'], models['cached']
            assert np.array_equal(a.columns, b.columns)
            assert a.base.group_slots == b.base.group_slots
            differences = []
            rng = np.random.default_rng(20261001)
            for offset in [np.zeros(len(a.initial)), rng.normal(size=len(a.initial))*.001]:
                va, ga = a.evaluate(a.initial+offset)
                vb, gb = b.evaluate(b.initial+offset)
                differences.append((abs(va-vb), float(np.max(np.abs(ga-gb)))))
            assert max(v for v, _ in differences) < 1e-9
            assert max(g for _, g in differences) < 1e-9
            assert np.array_equal(context.initial, original_initial)
            assert context.assignments == original_assignments
            assert context.group_slots == original_slots
            rows.append(dict(unit=unit, case=label, build_order=order,
                original_build_s=durations['original'], cached_build_s=durations['cached'],
                maximum_objective_difference=max(v for v, _ in differences),
                maximum_gradient_difference=max(g for _, g in differences)))
        # Shared memoization must not alter the context's own model result.
        value = parent.evaluate(np.asarray(receipt['mean']), gradient=False)[0]
        assert abs(value-receipt['final_objective']) < 1e-7
        try:
            Cached('different-scan', context=context)
        except ValueError:
            pass
        else:
            raise AssertionError('cross-scan context was accepted')
    verify_sources(sources)
    result = dict(rows=rows, source_sha256=sources,
        median_original_build_s=float(np.median([r['original_build_s'] for r in rows])),
        median_cached_build_s=float(np.median([r['cached_build_s'] for r in rows])),
        qualification='Paired construction microbenchmark, alternating order,19cases/12scans. '
        'Context preparation excluded from cached construction timing; must be paid once per '
        'scan. Same objective/gradient at two states per case and preserved parent context. '
        'No fitting, geography, total scan runtime or calibration claim.')
    output = HERE/'candidate-cached-audit-v1.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'source_sha256'}, indent=2))


if __name__ == '__main__':
    main()
