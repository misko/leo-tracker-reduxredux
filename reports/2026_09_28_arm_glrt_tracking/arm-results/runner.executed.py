"""Serial CPU0 tracking tests with saved IQ only; no radio access."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import shlex
import subprocess
import tarfile
import time
from pathlib import Path

import evaluate
import numpy as np

HERE = Path(__file__).resolve().parent
INPUTS = Path("/var/tmp/leo-ds7-large-arm-20260928")
ORACLE = Path("/var/tmp/leo-arm-full-search-oracle-allrates")
BASELINE = HERE.parent / "2026_09_28_ds7_large_arm/baseline-01/rows.jsonl"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(build: Path, output: Path, refreshes: list[int], radius: int, fallback: int):
    transport_path = HERE.parent / "2026_09_27_plutoplus_static_arm/concurrent/run_phase.py"
    spec = importlib.util.spec_from_file_location("tracking_transport", transport_path)
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    receipt = json.loads((build / "build.json").read_text())
    if not receipt["arm"]:
        raise ValueError("ARM build required")
    output.mkdir(parents=True, exist_ok=False)
    contexts = json.loads((INPUTS / "inputs.json").read_text())["rows"]
    cases = [
        next(r for r in contexts if r["rate_hz"] == 2500000 and r["target"]["edge"] == edge)
        for edge in ("lower", "upper")
    ]
    oracle = json.loads((ORACLE / "oracle.json").read_text())
    templates = {
        c["context"]["target"]["edge"]: c["templates"]
        for c in oracle["cases"]
        if c["context"]["rate_hz"] == 2500000
    }
    payload = {
        "tracking_probe": (build / "tracking_probe").read_bytes(),
        "test_tracking": (build / "test_tracking").read_bytes(),
    }
    for name in payload:
        if sha(payload[name]) != receipt["binary_sha256"][name]:
            raise ValueError("Build binary hash mismatch")
    baseline = {}
    for row in cases:
        edge = row["target"]["edge"]
        if sha((INPUTS / row["file"]).read_bytes()) != row["sha256"]:
            raise ValueError("Saved IQ hash mismatch")
        payload[f"{edge}.ci16"] = (
            np.load(INPUTS / row["file"], allow_pickle=False).astype("<i2").tobytes()
        )
        for key in ("exact", "control"):
            reference = templates[edge][key]
            data = (ORACLE / reference["file"]).read_bytes()
            if sha(data) != reference["sha256"]:
                raise ValueError("Template hash mismatch")
            payload[f"{edge}-{key}.c128"] = data
        baseline[edge] = evaluate.sealed_baseline(BASELINE, row)
    tar = io.BytesIO()
    with tarfile.open(fileobj=tar, mode="w:gz") as archive:
        for name, data in payload.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755 if name in ("tracking_probe", "test_tracking") else 0o644
            archive.addfile(info, io.BytesIO(data))
    remote_dir = f"/mnt/glrtbench/tracking-{time.time_ns()}"
    prefix = f"cd {shlex.quote(remote_dir)} && "
    subprocess.run(
        [*transport.SSH, f"mkdir {shlex.quote(remote_dir)} && " + prefix + "gzip -dc | tar -xf -"],
        input=tar.getvalue(),
        check=True,
        timeout=180,
    )
    observed = subprocess.check_output(
        [*transport.SSH, prefix + "sha256sum *"], text=True, timeout=20
    )
    expected = {name: sha(data) for name, data in payload.items()}
    if {line.split()[1]: line.split()[0] for line in observed.splitlines()} != expected:
        raise ValueError("Remote payload hash mismatch")
    unit = subprocess.run(
        [*transport.SSH, prefix + "./test_tracking"], capture_output=True, timeout=30
    )
    (output / "unit.stdout").write_bytes(unit.stdout)
    (output / "unit.stderr").write_bytes(unit.stderr)
    unit.check_returncode()
    manifest = {
        "schema": "arm-glrt-tracking-arm/v1",
        "complete": False,
        "selected": cases,
        "refreshes": refreshes,
        "radius": radius,
        "fallback": fallback,
        "cpu": 0,
        "simultaneous_capture": False,
        "saved_iq_only": True,
        "remote_directory": remote_dir,
        "payload_sha256": expected,
        "build_receipt_sha256": sha((build / "build.json").read_bytes()),
        "runner_sha256": sha(Path(__file__).read_bytes()),
        "completed_cases": 0,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with (output / "results.jsonl").open("w") as stream:
        for refresh in refreshes:
            for row in cases:
                edge = row["target"]["edge"]
                arguments = [
                    "./tracking_probe",
                    "2500000",
                    f"{edge}-exact.c128",
                    f"{edge}-control.c128",
                    f"{edge}.ci16",
                    str(refresh),
                    str(radius),
                    str(fallback),
                ]
                command = prefix + shlex.join(arguments)
                completed = subprocess.run(
                    [*transport.SSH, command], capture_output=True, text=True, timeout=180
                )
                label = f"refresh-{refresh}-{edge}"
                (output / f"{label}.stdout").write_text(completed.stdout)
                (output / f"{label}.stderr").write_text(completed.stderr)
                completed.check_returncode()
                records = [json.loads(line) for line in completed.stdout.splitlines()]
                windows = [r for r in records if r.get("type") == "window"]
                audit = evaluate.score(windows, baseline[edge])
                result = {
                    "context": row,
                    "refresh": refresh,
                    "radius": radius,
                    "fallback": fallback,
                    "command": command,
                    "records": records,
                    "audit": audit,
                }
                stream.write(json.dumps(result) + "\n")
                stream.flush()
                manifest["completed_cases"] += 1
                (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
                print(label, audit["counts"], flush=True)
    manifest["complete"] = True
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--refresh", type=int, nargs="+", default=[1, 2, 3, 5, 11])
    parser.add_argument("--radius", type=int, choices=[0, 1], default=1)
    parser.add_argument("--fallback", type=int, choices=[0, 1], default=0)
    args = parser.parse_args()
    run(args.build.resolve(), args.output.resolve(), args.refresh, args.radius, args.fallback)
