"""Run the eight paired local joint fits once, with per-record resource caps."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
(HERE / "results").mkdir(exist_ok=False)
(HERE / "receipts").mkdir(exist_ok=False)
paths = [
    Path(__file__),
    HERE / "run.py",
    HERE / "PROTOCOL.md",
    ROOT / "tools/ds7_shared_slope_shadow.py",
    ROOT / "tools/ds7_residual_audit.py",
    ROOT / "tools/ds7_fast_baseline_adapter.py",
    ROOT / "tools/ds7_baseline_adapter.py",
    ROOT / "tests/research/test_ds7_shared_slope_shadow.py",
    ROOT / "tools/ds7_slope_identifiability.py",
    ROOT / "tests/research/test_ds7_slope_identifiability.py",
    ROOT / "tools/ds7_joint_slope_fit.py",
    ROOT / "tests/research/test_ds7_joint_slope_fit.py",
    ROOT / "reports/2026_09_27_ds7_full88/residual/independent-response-index.json",
    ROOT / "reports/2026_09_27_ds7_full88/solver/joint-v1/full88/request.json",
    ROOT / "reports/2026_09_27_ds7_full88/solver/joint-v1/full88/response.json",
]
for ordinal in range(1, 9):
    unit = f"single-{ordinal:03d}"
    receipt = HERE / "receipts" / unit
    receipt.mkdir()
    independent = json.loads(
        (
            ROOT / "reports/2026_09_27_ds7_full88/residual/independent-response-index.json"
        ).read_text()
    )["responses"][ordinal - 1]
    bound_paths = paths + [
        Path(independent["response_path"]),
        Path(independent["response_path"]).with_name("request.json"),
        ROOT / f"reports/2026_09_28_subkm_residual_transfer/results/{unit}.json",
        ROOT
        / (
            "reports/2026_09_28_subkm_shared_slope/results.json"
            if ordinal == 1
            else f"reports/2026_09_28_subkm_slope_transfer/results/{unit}.json"
        ),
    ]
    command = [
        "sudo",
        "-n",
        "/usr/bin/time",
        "-v",
        "-o",
        str(receipt / "resources.txt"),
        "timeout",
        "--kill-after=5s",
        "180s",
        "prlimit",
        "--as=4294967296",
        "nice",
        "-n",
        "19",
        "env",
        "OPENBLAS_NUM_THREADS=1",
        "OMP_NUM_THREADS=1",
        "MKL_NUM_THREADS=1",
        "/opt/leo-tracker/current-api/.venv/bin/python",
        str(HERE / "run.py"),
        str(ordinal),
    ]
    with (receipt / "launch.json").open("x") as stream:
        json.dump(
            {
                "command": command,
                "sha256": {
                    str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in bound_paths
                },
            },
            stream,
            indent=2,
        )
    print("starting", unit, flush=True)
    with (receipt / "terminal.log").open("x") as stream:
        result = subprocess.run(
            command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=False
        )
    (receipt / "exit-code.txt").write_text(str(result.returncode) + "\n")
    print("finished", unit, "exit", result.returncode, flush=True)
    # Continue the fixed panel; preserve failures and never retry a record.
