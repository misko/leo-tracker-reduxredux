#!/usr/bin/env python3
"""Build a distinct persistent worker from an already qualified candidate tree."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
OPTIMIZE = HERE.parent
CONCURRENT = OPTIMIZE.parent / "concurrent"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", nargs="?", default="rankconversion")
    parser.add_argument("--recorded-arrivals", action="store_true")
    args = parser.parse_args()
    if not args.candidate.replace("_", "").isalnum():
        raise ValueError("candidate")
    root = OPTIMIZE / "work" / args.candidate
    source = root / "src/native_presence"
    candidate_receipt = root / "arm.build.json"
    qualification = root / "arm-check/completion.json"
    paced = CONCURRENT / ("paced.c" if args.recorded_arrivals else "paced_v1.c")
    flavor = "cadence" if args.recorded_arrivals else "paced"
    output_dir = HERE / "build"
    output_dir.mkdir(exist_ok=True)
    output = output_dir / f"{args.candidate}-{flavor}-arm"
    receipt_path = output.with_suffix(".build.json")
    stderr_path = output.with_suffix(".build.stderr")
    if output.exists() or receipt_path.exists() or stderr_path.exists():
        raise FileExistsError("persistent worker artifact already exists")
    receipt = json.loads(candidate_receipt.read_text())
    qualified = json.loads(qualification.read_text())
    if not qualified.get("complete") or not qualified.get("passed"):
        raise RuntimeError("candidate ARM qualification has not passed")
    expected_sources = receipt["sources"]
    current_sources = {str(path.relative_to(root)): sha(path)
                       for path in sorted((root / "src").rglob("*")) if path.is_file()}
    if current_sources != expected_sources:
        raise RuntimeError("candidate sources differ from qualified build")
    command = receipt["command"][:]
    probe = str(source / "probe.c")
    if command.count(probe) != 1 or command[-2] != "-o":
        raise RuntimeError("unexpected candidate build command")
    command[command.index(probe)] = str(paced)
    command[-1] = str(output)
    before = current_sources.copy()
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
    stderr_path.write_text(completed.stderr)
    if completed.returncode:
        raise RuntimeError(completed.stderr)
    after = {str(path.relative_to(root)): sha(path)
             for path in sorted((root / "src").rglob("*")) if path.is_file()}
    if before != after:
        output.unlink(missing_ok=True)
        raise RuntimeError("candidate sources changed during worker build")
    worker_receipt = {
        "schema": "org.leo.research.optimized-persistent-worker-build/v1",
        "candidate": args.candidate,
        "flavor": flavor,
        "recorded_arrivals": args.recorded_arrivals,
        "command": command,
        "binary": str(output),
        "binary_sha256": sha(output),
        "paced_source": str(paced),
        "paced_source_sha256": sha(paced),
        "candidate_build_receipt": str(candidate_receipt),
        "candidate_build_receipt_sha256": sha(candidate_receipt),
        "candidate_binary_sha256": receipt["binary_sha256"],
        "candidate_sources": before,
        "qualification": str(qualification),
        "qualification_sha256": sha(qualification),
        "qualification_cases": qualified["cases"],
        "hardware_executed": False,
    }
    receipt_path.write_text(json.dumps(worker_receipt, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
