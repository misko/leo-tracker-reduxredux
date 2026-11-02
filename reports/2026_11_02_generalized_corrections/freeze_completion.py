"""Prospective operational completion plan; no candidate or GPS selection."""
import hashlib
import json
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    original=ROOT/'execution_protocol.json'
    policy=json.loads(original.read_text())
    assert (ROOT/'evaluation/execution_started.json').exists()
    assert not (ROOT/'evaluation/results.json').exists()
    assert not (ROOT/'position_evaluation_binding.json').exists()
    for path,digest in policy['source_sha256'].items():
        assert sha(Path(path))==digest,path
    sources=[ROOT/'evaluation/complete_coverage.py',ROOT/'evaluation/test_completion.py',Path(__file__).resolve()]
    protocol=dict(created_utc_ns=time.time_ns(),
        reason='Observed throughput would leave a large unattempted subset; complete only cases never started, before opening candidate geographic outcomes',
        scientific_policy_changed=False, per_cell_budget_changed=False,
        retried_actual_attempts_allowed=False, original_execution_window_unchanged=True,
        coverage_completion=dict(original_protocol_path=str(original),original_protocol_sha256=sha(original),
            allowed_waves=['wave2','wave3'],workers=16,wave_seconds=1200),
        source_sha256={str(p):sha(p) for p in sources},
        eligibility='No prior worker receipt, elapsed marker, intermediate or non-manager case artifact; all prior source ledgers sealed and workers joined',
        reporting='Retain exact original terminal/partial decisions for every started case; late waves cannot replace them; combine every available case exactly once')
    destination=ROOT/'coverage_protocol.json'
    assert not destination.exists()
    destination.write_text(json.dumps(protocol,indent=2)+'\n')
    print('Coverage protocol',sha(destination))


if __name__=='__main__':
    main()
