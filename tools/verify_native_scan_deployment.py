"""Bounded installed canaries under the existing scanner authority and locks."""

import argparse
import json
import subprocess
from pathlib import Path

from leo.acquisition.authority import (
    CaptureTaskKind, LocalCaptureAuthority, RadioResource,
)
from leo.storage.short_window import ShortWindowReader


def verify_recording(folder):
    checkpoint = json.loads((folder / "run.json").read_bytes())
    assert checkpoint["state"] == "stopped" and not checkpoint["fault"], checkpoint
    assert checkpoint["captured_windows"] == checkpoint["durable_windows"] >= 8
    assert checkpoint["device_terminal"]["error"] == 0
    assert checkpoint["host_restoration"]["fastlock_inactive"]
    count = 0
    targets = set()
    for path in sorted(folder.glob("*-segment-*")):
        reader = ShortWindowReader(path)
        assert reader.manifest.schema_version == 2
        assert reader.manifest.sample_rate_hz == 10_000_000
        assert reader.manifest.status == "complete"
        for window in reader.windows():
            a = window.index.acquisition
            receipt = json.loads(a["retune_receipt"])
            assert window.samples.shape == (200_000, 2, 2)
            assert a["sample_end"] - a["sample_start"] == 200_000
            assert a["complete"] and a["listen_ms"] == 20
            assert receipt["minimum_post_recall_guard_samples"] == 200_000
            assert receipt["post_recall_guard_satisfied"]
            targets.add(window.index.target_id)
            count += 1
    assert count == checkpoint["captured_windows"]
    assert len(targets) == 8
    return {"windows": count, "targets": len(targets), "sample_rate_hz": 10_000_000,
            "raw_payload_bytes": count * 1_600_000, "restored": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--mode", choices=("fast", "adaptive"), required=True)
    args = parser.parse_args()
    config = json.loads((args.release / "capture-config.json").read_bytes())
    authority = LocalCaptureAuthority(Path(config["bulk_root"]) / "control", (
        RadioResource(config["serial"], config["serial"], config["uri"]),))
    results = {}
    for edge in (("lower", "upper") if args.mode == "fast" else ("adaptive",)):
        identifier = f"native10-canary-{edge}"
        command = config[args.mode]["command"].copy()
        if args.mode == "fast":
            command[command.index("--seconds") + 1] = "4"
            command[command.index("--root") + 1] = str(args.evidence / "recordings")
            bulk = command.index("--bulk-root")
            del command[bulk:bulk + 2]
            command = [part.replace("{campaign}", identifier).replace("{edge}", edge) for part in command]
        else:
            command[command.index("--duration-ms") + 1] = "12000"
        with authority.claim((config["serial"],), task_id=identifier,
                             task_kind=CaptureTaskKind.SCANNER_SWEEP):
            with (args.evidence / f"{identifier}.log").open("x") as output:
                subprocess.run(command, stdout=output, stderr=subprocess.STDOUT,
                               check=True, timeout=120)
        if args.mode == "fast":
            folder = args.evidence / "recordings" / f"{identifier}-1-{edge}"
            results[edge] = verify_recording(folder)
        else:
            results[edge] = {"recorder_exit": 0, "duration_ms": 12000, "sample_rate_hz": 10_000_000}
    (args.evidence / f"{args.mode}-verification.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results), flush=True)


if __name__ == "__main__":
    main()
