"""Read both complete saved captures through authenticated, memory-capped ordinary GLRT."""

import argparse
from functools import partial
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from ..__main__ import local_output, save_json
from . import iq_joint_resources as resources
from . import iq_joint_trial as iq
from . import raw_robust, raw_stream_reader, raw_stream_trial, recording_to_v5
from .full_v5_check import NATIVE_LIBRARY, _sha
from .secant_end_to_end_worker import cpu_s, stamp

REPORT = iq.REPORT.parent.parent / "recovery/clock-chain"
CPUS = (4, 5)
WALL_CAP = 540
RAW_CAP = dict(zip(iq.CASES, (260, 230), strict=True))
RUNNER_RECEIPT = "raw-runner.json"


def _finish(folder, case, deadline, detector, *, begin, cpu, expected):
    raw_envelope = stamp(begin, cpu)
    assembly_start, assembly_cpu = perf_counter(), cpu_s()
    logs = [folder / f"replayed-{lane}.log" for lane in range(2)]
    lanes = [raw_stream_trial.lane_metrics(log) for log in logs]
    raw = raw_robust.assemble_raw(folder, case, deadline, detector)
    if (
        raw["native_sha256"] != expected["ordinary_native_sha256"]
        or sum(lane["decoded_bytes"] for lane in lanes) != raw["iq_bytes"]
        or sum(lane["decoded_visits"] for lane in lanes) != expected["window_count"]
        or any(lane["largest_read_bytes"] > raw_stream_reader.READ_BYTES for lane in lanes)
    ):
        raise ValueError("Fresh factor product differs from its complete ordinary authority")
    save_json(
        folder / "raw-stages.json",
        dict(
            raw=raw,
            raw_envelope=raw_envelope,
            factor_assembly=stamp(assembly_start, assembly_cpu),
            raw_lanes=lanes,
            raw_memory=resources.raw_memory(logs),
            cpus=CPUS,
        ),
    )


def run(work):
    resources.cap_address_space(resources.ASSEMBLY_AS_MIB)
    existing = iq.read(iq.SEAL)
    if iq.encoded(existing) != iq.encoded(iq.source_lock(iq.joint.BUNDLE)):
        raise ValueError("Complete ordinary IQ authority does not match the frozen build")
    runner = Path(__file__)
    runner_sha = _sha(runner)
    started = perf_counter()
    for ident in iq.CASES:
        begin, cpu = perf_counter(), cpu_s()
        budget = min(RAW_CAP[ident], int(WALL_CAP - (begin - started)))
        if budget <= 0:
            break
        finish = partial(_finish, begin=begin, cpu=cpu, expected=existing["inputs"][ident])
        folder = work / ident
        try:
            with patch.object(recording_to_v5, "MODULE", iq.MODULE):
                recording_to_v5.run_recording(
                    ident, folder, CPUS, budget, NATIVE_LIBRARY, finish=finish
                )
        except (OSError, ValueError, TimeoutError) as exc:
            print(ident, "complete raw replay unavailable", str(exc), flush=True)
            exits = folder / "raw-worker-exits.json"
            save_json(
                work / f"{ident}-raw-failure.json",
                dict(
                    wall_s=perf_counter() - begin,
                    reason=str(exc),
                    exits=iq.read(exits) if exits.exists() else None,
                ),
            )
    if _sha(runner) != runner_sha:
        raise ValueError("Raw runner changed during the complete replay")
    save_json(work / RUNNER_RECEIPT, {runner.name: runner_sha})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=Path)
    args = parser.parse_args()
    path = local_output(args.work)
    path.mkdir(parents=True, exist_ok=False)
    run(path)


if __name__ == "__main__":
    main()
