"""Seal the compact physical receiver clock over all original native packets."""

import argparse
from pathlib import Path
from unittest.mock import patch

from ..variants import compact_clock
from . import native_clock_full as smooth

WORKER = Path(__file__).with_name("compact_clock_worker.py")
REPORT = smooth.base.native.ROOT / "reports/2026_11_19_receiver_screening/refinement/compact-clock"
WORK = smooth.WORK.with_name("native-compact-clock")
_PLAN, _COMMAND, _BIND = smooth.prepare, smooth.command, smooth.bindings


def prepare(bundle):
    base, jobs = _PLAN(bundle)
    clock_lock = smooth.REPORT / "prediction-lock.json"
    lock = smooth.phase._read(clock_lock)
    smooth.base.secant_full._verify_files(smooth.REPORT, lock["files"])
    plan = dict(
        base,
        smooth_panel_sha256=smooth.phase.digest(clock_lock),
        compact_protocol_sha256=smooth.phase.digest(REPORT / "PROTOCOL.md"),
        compact_source_sha256=smooth.phase.digest(Path(compact_clock.__file__)),
        compact_worker_sha256=smooth.phase.digest(WORKER),
        compact_runner_sha256=smooth.phase.digest(Path(__file__)),
        compact_model=dict(
            knots_s=compact_clock.KNOTS_S.tolist(),
            slope_sd_hz_per_s=compact_clock.RATE_SD_HZ_S,
            second_difference_sd_hz=compact_clock.ACCELERATION_SD_HZ,
            second_difference_adjacent_correlation=0.25,
            rf_reference_hz=compact_clock.smooth.REFERENCE_HZ,
            static_mixer_offsets=4,
            oscillator_coordinates=8,
        ),
    )
    return plan, jobs


def command(cpu, paths, bundle):
    argv = _COMMAND(cpu, paths, bundle)
    argv[argv.index(str(smooth.WORKER))] = str(WORKER)
    argv[-3:-3] = [
        "--ro-bind", str(Path(compact_clock.__file__)),
        "/worker/tools/pipeline_eval/variants/compact_clock.py",
    ]
    return argv


def bindings(query):
    return dict(_BIND(query), method=compact_clock.METHOD, variant=compact_clock.METHOD)


def run(work, bundle):
    with (
        patch.object(smooth, "prepare", prepare),
        patch.object(smooth, "command", command),
        patch.object(smooth, "bindings", bindings),
    ):
        smooth.run(work, bundle, REPORT)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--bundle", type=Path, default=smooth.base.BUNDLE)
    args = parser.parse_args()
    run(args.work, args.bundle)
