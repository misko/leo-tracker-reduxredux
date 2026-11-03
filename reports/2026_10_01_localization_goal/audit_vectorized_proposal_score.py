"""Compare existing scalar and vectorized objectives on all144sealed alternatives."""
import json
import time
from pathlib import Path

import numpy as np
from candidate_cached_joint import CandidateJointObjective
from candidate_joint_expansion_adapter import CandidateJointObjective as Original
from regression_batch import digest, verify_sources

from leo.analysis.localization_epoch_profile import profile_unused_epochs

HERE = Path(__file__).resolve().parent


def main():
    freeze = HERE/'proposal-coverage-v1/sources.json'
    assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
    frozen = json.loads(freeze.read_text())
    sources = frozen['source_sha256']
    sources[str(Path(__file__))] = digest(__file__)
    verify_sources(sources)
    rows = []
    for unit in frozen['units']:
        audit_path = freeze.parent/(unit+'.json')
        assert digest(audit_path) == audit_path.with_suffix('.sha256').read_text().strip()
        audit = json.loads(audit_path.read_text())
        assert audit['complete']
        parent_path = HERE/'alternating-expansion-v1'/(unit+'-candidate.json')
        assert digest(parent_path) == audit['parent_sha256']
        parent = json.loads(parent_path.read_text())
        context = Original(unit).base
        for proposal in audit['rows']:
            choices = parent['assignments'].copy()
            choices[proposal['track']] = proposal['new_identity']
            state, prior_gain = profile_unused_epochs(
                parent['full_state'], choices, len(parent['full_state'])-5)
            assert abs(prior_gain-proposal['profiled_prior_gain']) < 1e-7
            model = CandidateJointObjective(unit, state=state, assignments=choices, context=context)
            times, values = {}, {}
            order = ['scalar', 'vectorized'] if len(rows) % 2 else ['vectorized', 'scalar']
            for label in order:
                started = time.perf_counter()
                if label == 'scalar':
                    value = model.evaluate(model.initial, gradient=False)[0]
                else:
                    training, candidate = model.base.components(state[:2])
                    value = training-candidate
                times[label] = time.perf_counter()-started
                values[label] = value
            difference = abs(values['scalar']-values['vectorized'])
            assert difference < 1e-7
            expected = parent['final_objective']-proposal['full_objective_gain']
            assert abs(expected-values['scalar']) < 1e-7
            rows.append(dict(unit=unit, track=proposal['track'], difference=difference,
                             scalar_s=times['scalar'], vectorized_s=times['vectorized']))
    verify_sources(sources)
    result = dict(rows=rows, source_sha256=sources,
        maximum_difference=max(r['difference'] for r in rows),
        median_scalar_s=float(np.median([r['scalar_s'] for r in rows])),
        median_vectorized_s=float(np.median([r['vectorized_s'] for r in rows])),
        qualification='144fixed-state alternatives from3sealed scans, alternating score order; '
        'construction excluded. Existing vectorized spatial objective evaluated at its full '
        'initial state only, including all nuisance parameters. This equivalence does not '
        'permit using fixed-nuisance spatial scoring for a changed continuous state. No GPS '
        'or fitting; no total scan runtime claim.')
    output = HERE/'vectorized-proposal-score-v1.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ['rows', 'source_sha256']}, indent=2))


if __name__ == '__main__':
    main()
