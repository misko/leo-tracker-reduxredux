"""Guarded ALGO04 replay of a completed ALGO03 schedule; no truth or new catalogue."""

import argparse
import shutil
import signal
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import algo03_shadow_worker as worker
from algo03_shadow_worker import read, write
from algo04_cache import digest, relocate

from leo.application.automatic_fast_graph import execute


def overflow(value):
    if isinstance(value, dict):
        return value.get("phase_outside_reference_window") is True or any(
            overflow(v) for v in value.values()
        )
    return isinstance(value, list) and any(overflow(v) for v in value)


def run(output, maximum_seconds):
    export = read(output / "source-export/descriptor.json")
    export_root = Path(export["root"])
    if export_root != output / "source-export":
        raise ValueError("Recovery export root is not this private export")
    for name, expected in export["files"].items():
        member = export_root / name
        if (
            Path(name).is_absolute()
            or ".." in Path(name).parts
            or digest(member) != expected.removeprefix("sha256:")
        ):
            raise ValueError("Recovery export member changed")
    src = output / "cache"
    files = {
        name.removeprefix("recovery/"): sha
        for name, sha in export["files"].items()
        if name.startswith("recovery/")
    }
    receipt = relocate(export_root / "recovery", src, export["source_recovery_root"], files)
    write(output / "cache-relocation.json", receipt)
    original = read(src / "decision.json")
    shutil.copytree(src / "snapshot", output / "snapshot")
    completed = {
        a["track_id"]
        for a in original["attempts"]
        if (src / a["track_id"] / "annotation/result.json").exists()
    }
    stages, charged = [], 0.0
    originals = {s["name"]: s for s in original["stages"]}
    write(
        output / "protocol.json",
        dict(
            policy="algo04-conditional-numerical-replay-v1",
            completed_target_ids=sorted(completed),
            reference_limit_s=30,
            centered_gradient_step_km=0.001,
            maxls=40,
            maxiter=48,
            total_objective_calls_per_round=240,
            phase_rounds=5,
            maximum_seconds=min(maximum_seconds, original["maximum_seconds"]),
            original_stage_time_charged=True,
            causal_bank_unchanged=True,
            no_GPS_inference=True,
            same_candidate_alias_partition_inputs=True,
        ),
    )
    original_select, original_execute, original_time = (
        worker.select_targets,
        worker.execute,
        worker.time,
    )

    def select(inventory, limit=8):
        rows, count = original_select(inventory, limit)
        return [r for r in rows if r["track_id"] in completed], count

    def staged(command, *, log, timeout):
        nonlocal charged
        script, args = Path(command[2]).name, command[3:]

        def option(name):
            return Path(args[args.index(name) + 1])

        stage_name = Path(log.name).stem
        dest = option("--output")
        old = src / dest.relative_to(output)
        reuse = False
        reason = "numerical_dependency_changed"
        if script == "algo03_inventory.py":
            reuse, reason = True, "graph_and_original_baseline_unchanged"
        elif script == "annotate_predictive_only.py":
            reuse = not overflow(read(old / "result.json"))
            reason = (
                "all_saved_reference_updates_inside_15s"
                if reuse
                else "saved_phase_reference_clipped"
            )
        elif script == "include_predictive_annotations.py":
            changed = bool(read(option("--validation") / "protocol.json").get("numerical_replay"))
            reuse = (old / "control.json").exists() and not changed
            if reuse:
                reuse = not any(overflow(read(p)) for p in old.glob("*.json"))
            reason = "unchanged_shared_fit" if reuse else reason
        elif script == "audit_shared_predictive_inclusion.py":
            reuse = any(
                r["script"] == "include_predictive_annotations.py"
                and r["output"] == str(option("--trial"))
                and r["reused"]
                for r in stages
            )
            reason = "unchanged_shared_exact_replay"
        record = dict(script=script, output=str(dest), source=str(old), reused=reuse, reason=reason)
        began = time.monotonic()
        if reuse:
            if old.is_dir():
                shutil.copytree(old, dest)
            elif not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(old, dest)
            seconds = originals.get(stage_name, {}).get("seconds", 0.0)
            charged += max(0.0, seconds - (time.monotonic() - began))
            code = 0
            record["charged_original_seconds"] = seconds
        else:
            if script == "annotate_predictive_only.py":
                cmd = [
                    sys.executable,
                    "-B",
                    str(Path(__file__).with_name("algo04_annotation_replay.py")),
                    "--inventory",
                    str(option("--inventory")),
                    "--source",
                    str(old),
                    "--output",
                    str(dest),
                ]
            else:
                cmd = [
                    sys.executable,
                    "-B",
                    str(Path(__file__).with_name("algo04_numerical_stage.py")),
                    "--reference-limit-s",
                    "30",
                    "--centered-lbfgsb",
                    "--receipt",
                    str(output / "numerical-receipts" / (stage_name + ".json")),
                    str(Path(__file__).with_name(script)),
                    *args,
                ]
            record["command"] = cmd
            code = execute(cmd, log=log, timeout=timeout)
        record.update(returncode=code, wall_seconds=time.monotonic() - began)
        stages.append(record)
        write(output / "stage-cache" / f"{len(stages):03d}.json", record)
        return code

    try:
        worker.select_targets, worker.execute = select, staged
        worker.time = SimpleNamespace(monotonic=lambda: time.monotonic() + charged)
        return worker.run(output, min(maximum_seconds, original["maximum_seconds"]))
    finally:
        worker.select_targets, worker.execute, worker.time = (
            original_select,
            original_execute,
            original_time,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--maximum-seconds", type=int, choices=range(1, 1201), default=1170)
    args = parser.parse_args()

    def terminate(signum, frame):
        raise RuntimeError("ALGO04 recovery deadline")

    signal.signal(signal.SIGTERM, terminate)
    run(args.output.resolve(), args.maximum_seconds)
