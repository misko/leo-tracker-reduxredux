"""Isolated diagnostic entrypoint; all numerical children use the pinned worker."""
import json
import signal
import sys
from pathlib import Path

import algo03_shadow_worker as worker
from algo03_stage_clock_fixture import run_controlled

output = Path(sys.argv[1]).resolve(strict=True)
control = json.loads((output / 'clock-control.json').read_text())


def terminate(signum, frame):
    # BaseException propagates through the original executor's process-group
    # cleanup and cannot be swallowed as an ordinary failed numerical stage.
    raise SystemExit(124)


signal.signal(signal.SIGTERM, terminate)
result, receipt = run_controlled(worker, output, control['maximum_seconds'],
                                 control['schedule'], stop_after=control['stop_after'])
worker.write(output / 'clock-receipt.json', receipt)
print(json.dumps(dict(decision=result['decision'],
                      synthetic_seconds=receipt['synthetic_elapsed_seconds'],
                      real_wall_seconds=receipt['real_wall_seconds'])), flush=True)
