"""Run a receipted CPU-only unit executable on the development PLUTO+."""

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


def run(build, output, test):
    transport = Path(__file__).resolve().parent.parent / (
        "2026_09_27_plutoplus_static_arm/concurrent/run_phase.py"
    )
    spec = importlib.util.spec_from_file_location("transport", transport)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    receipt = json.loads((build / "build.json").read_text())
    binary = (build / test).read_bytes()
    digest = hashlib.sha256(binary).hexdigest()
    assert digest == receipt["binary_sha256"][test]
    output.mkdir(parents=True, exist_ok=False)
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        info = tarfile.TarInfo(test)
        info.size = len(binary)
        info.mode = 0o755
        archive.addfile(info, io.BytesIO(binary))
    remote = f"/mnt/glrtbench/coarse-unit-{time.time_ns()}"
    prefix = f"cd {shlex.quote(remote)} && "
    subprocess.run(
        [*module.SSH, f"mkdir {shlex.quote(remote)} && " + prefix + "gzip -dc | tar -xf -"],
        input=payload.getvalue(),
        check=True,
        timeout=30,
    )
    observed = subprocess.check_output(
        [*module.SSH, prefix + "sha256sum " + shlex.quote(test)],
        text=True,
        timeout=15,
    ).split()[0]
    assert observed == digest
    result = subprocess.run(
        [*module.SSH, prefix + "./" + shlex.quote(test)],
        text=True,
        capture_output=True,
        timeout=120,
    )
    record = {
        "binary_sha256": digest,
        "remote_directory": remote,
        "build_receipt_sha256": hashlib.sha256((build / "build.json").read_bytes()).hexdigest(),
        "test": test,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "rf_access": False,
    }
    (output / "result.json").write_text(json.dumps(record, indent=2) + "\n")
    result.check_returncode()
    print(result.stdout, end="")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--test", default="test_coarse_tile")
    args = parser.parse_args()
    run(args.build.resolve(), args.output.resolve(), args.test)
