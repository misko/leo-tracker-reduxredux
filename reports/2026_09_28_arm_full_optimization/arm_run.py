"""Run only saved fixture probes on PLUTO+ CPU0; never access RF devices."""

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

HERE = Path(__file__).resolve().parent


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def run(build: Path, oracle: Path, output: Path, repeats: int):
    if not 1 <= repeats <= 10:
        raise ValueError("Keep ARM runs bounded to 1..10 repeats")
    compare = module("full_compare", HERE / "compare.py")
    transport = module(
        "old_transport", HERE.parent / "2026_09_27_plutoplus_static_arm/concurrent/run_phase.py"
    )
    output.mkdir(parents=True, exist_ok=False)
    remote_dir = f"/mnt/glrtbench/full-search-{time.time_ns()}"
    manifest = json.loads((oracle / "oracle.json").read_text())
    for case in manifest["cases"]:
        references = list(case["templates"].values())
        references.extend(rx["raw_probe"] for rx in case["receivers"])
        for reference in references:
            if (
                hashlib.sha256((oracle / reference["file"]).read_bytes()).hexdigest()
                != reference["sha256"]
            ):
                raise ValueError("Oracle sidecar hash mismatch")
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        archive.add(build / "probe", arcname="probe")
        for path in sorted(oracle.glob("*.c128")):
            archive.add(path, arcname=path.name)
    command = (
        f"mkdir {shlex.quote(remote_dir)} && cd {shlex.quote(remote_dir)} && gzip -dc | tar -xf -"
    )
    subprocess.run([*transport.SSH, command], input=payload.getvalue(), check=True, timeout=180)
    hashes = {"probe": hashlib.sha256((build / "probe").read_bytes()).hexdigest()}
    hashes.update(
        {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in oracle.glob("*.c128")}
    )
    remote_hashes = subprocess.check_output(
        [*transport.SSH, f"cd {shlex.quote(remote_dir)} && sha256sum probe *.c128"],
        text=True,
        timeout=15,
    )
    observed = {line.split()[1]: line.split()[0] for line in remote_hashes.splitlines()}
    if observed != hashes:
        raise ValueError("ARM payload hash mismatch")
    receipt = {
        "schema": "arm-full-search-execution/v1",
        "host": "192.168.1.15",
        "core": 0,
        "remote_directory": remote_dir,
        "payload_sha256": hashes,
        "repeats": repeats,
        "saved_iq_only": True,
        "simultaneous_capture": False,
        "complete": False,
        "passed": True,
        "oracle_sha256": hashlib.sha256((oracle / "oracle.json").read_bytes()).hexdigest(),
        "build_receipt_sha256": hashlib.sha256((build / "build.json").read_bytes()).hexdigest(),
    }
    (output / "run.json").write_text(json.dumps(receipt, indent=2) + "\n")
    with (output / "results.jsonl").open("w") as stream:
        for case in manifest["cases"]:
            for rx in case["receivers"]:
                label = (
                    f"{case['context']['rate_hz']}-"
                    f"{case['context']['target']['edge']}-rx{rx['receiver_id']}"
                )
                names = [case["templates"][k]["file"] for k in ("exact", "control")]
                args = [
                    "./probe",
                    str(case["context"]["rate_hz"]),
                    *names,
                    rx["raw_probe"]["file"],
                    label + ".f64",
                    str(repeats),
                ]
                command = f"cd {shlex.quote(remote_dir)} && " + shlex.join(args)
                result = subprocess.run(
                    [*transport.SSH, command], text=True, capture_output=True, timeout=180
                )
                (output / (label + ".stdout")).write_text(result.stdout)
                (output / (label + ".stderr")).write_text(result.stderr)
                result.check_returncode()
                native = json.loads(result.stdout)
                grid = subprocess.check_output(
                    [*transport.SSH, f"cat {shlex.quote(remote_dir + '/' + label + '.f64')}"],
                    timeout=30,
                )
                grid_path = output / (label + ".f64")
                grid_path.write_bytes(grid)
                parity = compare.compare_response(native, rx, grid_path, oracle)
                passed = parity["ordered_within_tolerance"] and parity["grid"]["within_tolerance"]
                receipt["passed"] = receipt["passed"] and passed
                record = {
                    "label": label,
                    "native": native,
                    "comparison": parity,
                    "command": command,
                    "passed": passed,
                }
                stream.write(json.dumps(record) + "\n")
                stream.flush()
                print(label, native["mean_cpu_ms"], flush=True)
    receipt["complete"] = True
    (output / "run.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if not receipt["passed"]:
        raise ValueError("ARM result does not match frozen oracle; inspect saved results")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--oracle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    run(args.build.resolve(), args.oracle.resolve(), args.output.resolve(), args.repeats)
