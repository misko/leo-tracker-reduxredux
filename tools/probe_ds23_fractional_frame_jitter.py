"""Same frozen jitter validation with correct fractional frame placement."""

from pathlib import Path
import probe_ds23_frame_timing_jitter as experiment
from ds23_fractional_frame_jitter import FractionalFrameJitterWorkspace
from run_algo01_ds23_sample import ROOT, read, write, sha


def main():
    experiment.OUT = ROOT/'reports/2026_10_20_ds23_fractional_frame_jitter'
    experiment.BULK = Path('/srv/bulk/leo/research/ds23-fractional-frame-jitter-20261020')
    experiment.FrameJitterWorkspace = FractionalFrameJitterWorkspace
    experiment.OUT.mkdir(exist_ok=True)
    workflow = dict(fractional_frame_placement=True, compared_against_fractional_zero_jitter=True,
        same_jobs_and_training_prediction_rules_as_rounded_test=True,
        rounded_test_protocol_sha256=sha(ROOT/'reports/2026_10_20_ds23_frame_timing_jitter/protocol.json'),
        source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/ds23_fractional_frame_jitter.py',
            ROOT/'tools/ds23_frame_timing_jitter.py', ROOT/'tools/probe_ds23_frame_timing_jitter.py',
            ROOT/'tools/decoupled_pilot_clocks.py']})
    target = experiment.OUT/'workflow_protocol.json'
    if target.exists() and read(target) != workflow:
        raise ValueError('fractional timing comparison changed')
    if not target.exists():
        write(target, workflow)
    experiment.main()


if __name__ == '__main__':
    main()
