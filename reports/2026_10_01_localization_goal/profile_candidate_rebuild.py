"""Bounded, reference-blind profile of four original reassociation model builds."""
import cProfile
import json
import pstats
import time
from pathlib import Path

import numpy as np
from candidate_reassociation_joint import CandidateJointObjective
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    freeze = HERE/'alternating-candidate-v1/sources.json'
    assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
    verify_sources(json.loads(freeze.read_text())['source_sha256'])
    rows = []
    for unit in ['DS10-F028', 'DS11-F018', 'DS9-F085', 'DS10-F149']:
        receipt = HERE/'alternating-candidate-v1'/(unit+'-control.json')
        assert digest(receipt) == receipt.with_suffix('.sha256').read_text().strip()
        parent = json.loads(receipt.read_text())
        profiler = cProfile.Profile()
        started = time.monotonic()
        profiler.enable()
        model = CandidateJointObjective(unit, state=parent['full_state'],
                                        assignments=parent['assignments'])
        profiler.disable()
        build_seconds = time.monotonic()-started
        started = time.monotonic()
        value, gradient = model.evaluate(np.asarray(parent['full_state'])[model.columns])
        evaluation_seconds = time.monotonic()-started
        assert abs(value-parent['final_objective']) < 1e-7
        stats = pstats.Stats(profiler).stats
        largest = sorted(stats.items(), key=lambda item: item[1][3], reverse=True)[:20]
        rows.append(dict(unit=unit, receipt_sha256=digest(receipt), build_s=build_seconds,
            evaluate_s=evaluation_seconds, objective=value,
            gradient_norm=float(np.linalg.norm(gradient)),
            cumulative_profile=[dict(file=k[0], line=k[1], function=k[2], calls=v[1],
                                     own_s=v[2], cumulative_s=v[3]) for k, v in largest]))
    result = dict(rows=rows, freeze_sha256=digest(freeze), profiler_sha256=digest(__file__),
        qualification='Four fixed-state builds under cProfile, no fitting or GPS. '
        'Profile overhead included; cumulative rows overlap and must not be summed.')
    output = HERE/'candidate-rebuild-profile-v1.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
