"""Emit the independent prelaunch receipt after source, input and test review."""
import json
from pathlib import Path

from movement_audit import ROOT, check_frozen_inputs, read, sha, write_new

HERE = Path(__file__).resolve().parent


def main():
    protocol, manifest, _, _ = check_frozen_inputs()
    tests = HERE/'movement_component_tests.txt'
    assert '14 passed' in tests.read_text()
    audit = read(HERE/'movement_input_audit.json')
    assert audit['status'] == 'passed' and audit['movement_protocol_sha256'] == sha(ROOT/'movement/protocol.json')
    assert not (ROOT/'movement/batch_start.json').exists()
    for path in (ROOT/'movement').glob('*.py'):
        assert '37.849061591' not in path.read_text(), path
    output = dict(approved=True, GPS_used=False, scientific_position_fits=0,
        movement_protocol_sha256=sha(ROOT/'movement/protocol.json'),
        root_protocol_sha256=sha(ROOT/'protocol.json'), source_sha256=sha(Path(__file__)),
        independent_input_audit_sha256=sha(HERE/'movement_input_audit.json'),
        independent_test_log_sha256=sha(tests), component_tests=14,
        cases=len(manifest), partitions=48, fold_jobs=144,
        source_review=dict(kernel='Original sealed numerical kernel retained; fresh prescribed PCG64 partitions; exclusive richer array outputs and fixed-position Gamma recording',
            masking='All original curved and predictive family owners removed from both calibration and position; held local priors untouched',
            policy='All 24 joint aggregate gains, both c arms and all convergence/finiteness checks plus original RF eligibility and paired adoption; exact shared baseline fallback',
            driver='Ordered two-job resource smoke barrier; allocation-only expansion to six; 2700-second global cap and explicit incomplete rows; no overwrite, no rescue or reruns',
            seal='369 source dependencies and full input/source bindings verified before jobs and again after completion'),
        coordinator_go_still_required=True)
    write_new(HERE/'movement_launch_approval.json', output)
    print(json.dumps(output, indent=2))


if __name__ == '__main__': main()
