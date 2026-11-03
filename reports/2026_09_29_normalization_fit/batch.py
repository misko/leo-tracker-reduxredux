import concurrent.futures
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"


def prepare():
    paths = list(HERE.glob("*.py")) + [HERE / "PROTOCOL.md"]
    for name in (
        "2026_09_29_curvature_scan_holdout/run.py",
        "2026_09_29_receiver_holdout/run.py",
        "2026_09_29_scan_holdout/timing.py",
        "2026_09_29_unassociated_trend/trend_mixture.py",
        "2026_09_29_frequency_contrast/contrast_position.py",
        "2026_09_29_donor_residual_transfer/plan.json",
        "2026_09_29_catalogue_recurrence/plan.json",
    ):
        paths.append(HERE.parent / name)
    for ds in ("DS7", "DS8", "DS9"):
        paths.append(HERE.parent / f"2026_09_29_scan_holdout/{ds}_early_8_d0.json")
    paths.extend(
        ROOT / name
        for name in ("tools/ds7_fast_baseline_adapter.py", "tools/ds7_baseline_adapter.py")
    )
    with (HERE / "manifest.json").open("x") as out:
        json.dump(
            dict(
                hashes={
                    str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in paths
                }
            ),
            out,
            indent=2,
        )


def worker(ds):
    try:
        result = subprocess.run(
            ["sudo", "-n", "env", "OPENBLAS_NUM_THREADS=1", PYTHON, str(HERE / "run.py"), ds],
            capture_output=True,
            text=True,
            timeout=300,
        )
        receipt = dict(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
    except subprocess.TimeoutExpired:
        receipt = dict(exit_code=None, timed_out=True)
    with (HERE / f"{ds}.receipt.json").open("x") as out:
        json.dump(receipt, out, indent=2)
    print(ds, receipt, flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare()
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(worker, ("DS7", "DS8", "DS9")))
