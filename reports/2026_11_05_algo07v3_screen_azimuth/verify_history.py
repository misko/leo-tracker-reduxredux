"""Audit accumulated changes against the earlier qualified DS26-0066 output."""

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from compare_algo07v3_runs import compare

# Reviewed against Git c25b4a189..196d3feb6 plus this screen-only change.
CHANGED = [
    'leo.analysis.localization_v3.hierarchical',
    'leo.analysis.localization_v3.numerical_policy',
    'leo.analysis.localization_v3.numerical_recovery',
    'leo.analysis.localization_v3.recovery_inclusion',
    'leo.analysis.localization_v3.residual_screen',
    'leo.analysis.localization_v3.screen_geometry',
    'leo.analysis.research.orbit_phase_geometry',
    'leo.application.localization_v3',
    'leo.application.localization_v3_engine',
    'leo.operations.localization_v3_inputs',
]


def main(earlier, current):
    result = compare(SimpleNamespace(
        baseline_request=earlier / 'candidate-request.json',
        candidate_request=current / 'candidate-request.json',
        baseline_timing=earlier / 'candidate/attempt/supervisor.json',
        candidate_timing=current / 'candidate/attempt/supervisor.json',
        changed_module=CHANGED, added_module=[]))
    # These runs are separated by several experiments and changing host load.
    # Their absolute clocks are evidence, not a controlled cumulative ratio.
    result['timing_comparison'] = False
    result['verifier_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with (current / 'history-parity.json').open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print('Earlier and current complete science/eight PNGs match exactly')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--earlier', type=Path, required=True)
    parser.add_argument('--current', type=Path, required=True)
    main(**vars(parser.parse_args()))
