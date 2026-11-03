"""Freeze and execute the 128-cell confirmation with two bounded workers."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREVIOUS = ROOT / "reports/2026_09_30_sacramento_model_comparison"
GAUSSIAN = ROOT / "reports/2026_09_30_gaussian_sum_64_scan"
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"
ARMS = ("C1", "M2", "M4", "M24")
EXPECTED_UNITS = 32
EXPECTED_CELLS = EXPECTED_UNITS * len(ARMS)
CONFIG_NAMES = ("plan.json", "selection.json", "method-configs.json", "preparation-audit.json")
REUSED_SOURCES = tuple(sorted(PREVIOUS.glob("*.py"))) + (
    GAUSSIAN / "physics.py",
    GAUSSIAN / "prior.py",
    ROOT / "src/leo/analysis/gaussian_sum_location.py",
    ROOT / "tools/ds7_export_baseline.py",
)


def digest(path: Path | str) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def units() -> list[str]:
    selected = json.loads((HERE / "selection.json").read_text())["selected"]
    groups = list(selected.values())
    result = [group[index]["unit_id"] for index in range(max(map(len, groups))) for group in groups if index < len(group)]
    if len(result) != EXPECTED_UNITS or len(set(result)) != EXPECTED_UNITS:
        raise ValueError("selection is not exactly 32 unique scans")
    return result


def freeze() -> None:
    source_paths = sorted(HERE.glob("*.py")) + [HERE / name for name in CONFIG_NAMES]
    source_paths += list(REUSED_SOURCES)
    source_paths.append(HERE / "tle-publications.jsonl")
    missing = [str(path) for path in source_paths if not path.exists()]
    if missing:
        raise FileNotFoundError("freeze inputs missing: " + ", ".join(missing))
    evidence_paths = sorted((HERE / "evidence").glob("*.json"))
    if len(evidence_paths) != 64:
        raise ValueError("freeze requires exactly 64 top-level evidence/orbit documents")
    preparation = json.loads((HERE / "preparation-audit.json").read_text())
    if preparation.get("all_32_passed") is not True:
        raise ValueError("preparation audit has not passed")
    prepared_rows = preparation.get("rows")
    if not isinstance(prepared_rows, list) or len(prepared_rows) != EXPECTED_UNITS:
        raise ValueError("preparation audit does not account for 32 units")
    if {row.get("unit") for row in prepared_rows} != set(units()):
        raise ValueError("preparation audit units differ from selection")
    document = {
        "schema": "covariance-epoch-execution-freeze/v1",
        "sources": {str(path): digest(path) for path in source_paths},
        "evidence": {str(path): digest(path) for path in evidence_paths},
        "arms": ARMS,
        "units": units(),
        "expected_cells": EXPECTED_CELLS,
        "fit_timeout_seconds": 90,
        "processes": 2,
        "numerical_threads": 1,
        "batch_scans_max": 8,
        "batch_wall_seconds": 900,
        "python": PYTHON,
        "truth_accessed": False,
        "preparation_audit_sha256": digest(HERE / "preparation-audit.json"),
    }
    write_new(HERE / "execution-freeze.json", document)


def verify() -> dict:
    frozen = json.loads((HERE / "execution-freeze.json").read_text())
    if frozen["arms"] != list(ARMS) or len(frozen["units"]) * len(frozen["arms"]) != EXPECTED_CELLS:
        raise ValueError("frozen matrix differs from 32 scans x 4 arms")
    for category in ("sources", "evidence"):
        for path, expected in frozen[category].items():
            if digest(path) != expected:
                raise ValueError(f"{category} changed after freeze: {path}")
    return frozen


def launch(unit: str, arm: str) -> dict:
    output = HERE / "runs" / f"{unit}-{arm}.json"
    receipt_path = output.with_suffix(".launch.json")
    if receipt_path.exists():
        return json.loads(receipt_path.read_text())
    if output.exists() or output.with_suffix(".seal.json").exists():
        raise FileExistsError("unreceipted prediction requires engineering audit")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "sudo", "-n", "timeout", "--kill-after=5s", "90s", "env",
        "OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1", "MKL_NUM_THREADS=1",
        f"PYTHONPATH={ROOT / 'src'}", PYTHON, str(HERE / "run_arm.py"),
        "--unit", unit, "--arm", arm, "--evidence-root", str(HERE / "evidence"),
        "--output", str(output),
    ]
    began = time.monotonic()
    log_path = output.with_suffix(".log")
    with log_path.open("x") as stream:
        process = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
    native = json.loads(output.read_text()) if output.exists() else {}
    receipt = {
        "unit": unit,
        "arm": arm,
        "returncode": process.returncode,
        "seconds": time.monotonic() - began,
        "command": command,
        "status": native.get("status", "timeout" if process.returncode == 124 else "error"),
        "prediction": str(output) if output.exists() else None,
        "log_sha256": digest(log_path),
        "execution_freeze_sha256": digest(HERE / "execution-freeze.json"),
    }
    write_new(receipt_path, receipt)
    print(json.dumps({key: receipt[key] for key in ("unit", "arm", "status", "seconds")}), flush=True)
    return receipt


def batch(start: int, count: int) -> None:
    if count < 1 or count > 8:
        raise ValueError("batch must contain one to eight scans")
    frozen = verify()
    selected_units = frozen["units"][start : start + count]
    pending = [
        (unit, arm)
        for unit in selected_units
        for arm in ARMS
        if not (HERE / "runs" / f"{unit}-{arm}.launch.json").exists()
    ]
    began = time.monotonic()
    completed = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for offset in range(0, len(pending), 2):
            if time.monotonic() - began > 800:
                break
            futures = [pool.submit(launch, *item) for item in pending[offset : offset + 2]]
            completed.extend(future.result() for future in as_completed(futures))
    verify()
    print(json.dumps({
        "batch_start": start,
        "count": count,
        "completed": len(completed),
        "remaining": len(pending) - len(completed),
        "seconds": time.monotonic() - began,
    }))


if __name__ == "__main__":
    if sys.argv[1:] == ["freeze"]:
        freeze()
    elif len(sys.argv) == 4 and sys.argv[1] == "batch":
        batch(int(sys.argv[2]), int(sys.argv[3]))
    else:
        raise ValueError("usage: run_panel.py freeze | batch START COUNT")
