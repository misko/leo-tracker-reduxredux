"""Bounded local cohort replay; every available recording follows one policy."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/associate_merged_track_catalogue.py"


def run(cohort, output, workers, latitude, longitude):
    output.mkdir(parents=True, exist_ok=False)
    coverage = json.loads((cohort / "coverage.json").read_text())
    eligible = [r for r in coverage if r["status"] == "tracks_evaluated"]
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    ledger = {r["source_id"]: dict(source_id=r["source_id"], status="pending") for r in coverage}
    for row in coverage:
        if row["status"] != "tracks_evaluated":
            ledger[row["source_id"]]["status"] = row["status"]

    def write():
        (output / "execution.json").write_text(json.dumps(list(ledger.values()), indent=2) + "\n")

    sources = [
        Path(__file__),
        TOOL,
        ROOT / "tools/analyze_dsx01_fixed_site.py",
        ROOT / "src/leo/analysis/research/component_frequency_bias.py",
        ROOT / "src/leo/analysis/research/track_catalogue_geometry.py",
    ]
    (output / "protocol.json").write_text(
        json.dumps(
            dict(
                source_sha256={
                    str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sources
                },
                workers=workers,
                stage_timeout_s=90,
                bias_sigma_hz=[0, 1000],
                grouping=["fragments", "merged"],
                rf_arms=["c0", "fitted_c"],
                evaluation_position=[latitude, longitude],
                position_mode="fixed-site diagnostic",
                identity_truth_available=False,
            ),
            indent=2,
        )
        + "\n"
    )
    write()

    def one(row):
        sid = row["source_id"]
        recording = cohort / sid
        bank = Path("/tmp") / f"ds22-merged-orbits-{sid}"
        commands = []
        if not (bank / "receipt.json").exists():
            commands.append(
                [
                    "sudo",
                    "-n",
                    "-u",
                    "leo",
                    "env",
                    "OPENBLAS_NUM_THREADS=1",
                    sys.executable,
                    str(TOOL),
                    "prepare",
                    "--recording",
                    str(recording),
                    "--output",
                    str(bank),
                ]
            )
        for sigma in (0, 1000):
            commands.append(
                [
                    sys.executable,
                    str(TOOL),
                    "associate",
                    "--recording",
                    str(recording),
                    "--inputs",
                    str(bank),
                    "--output",
                    str(output / sid / f"bias_{sigma}"),
                    "--latitude",
                    str(latitude),
                    "--longitude",
                    str(longitude),
                    "--component-bias-sigma-hz",
                    str(sigma),
                ]
            )
        logs = []
        for command in commands:
            try:
                result = subprocess.run(
                    command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=90
                )
                logs.append(
                    dict(
                        command=command,
                        returncode=result.returncode,
                        stdout=result.stdout,
                        stderr=result.stderr,
                    )
                )
                if result.returncode:
                    break
            except subprocess.TimeoutExpired as error:
                logs.append(
                    dict(
                        command=command, returncode=None, error=f"90-second stage timeout: {error}"
                    )
                )
                break
        (output / sid).mkdir(parents=True, exist_ok=True)
        (output / sid / "execution.json").write_text(json.dumps(logs, indent=2) + "\n")
        success = len(logs) == len(commands) and all(x["returncode"] == 0 for x in logs)
        return dict(
            source_id=sid,
            status="association_evaluated" if success else "failed",
            stages=len(logs),
            bank=str(bank),
            position_estimated=False,
        )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(one, row) for row in eligible]
        for future in as_completed(futures):
            row = future.result()
            ledger[row["source_id"]] = row
            write()
            done = sum(r["status"] == "association_evaluated" for r in ledger.values())
            failed = sum(r["status"] == "failed" for r in ledger.values())
            print(
                json.dumps(
                    dict(
                        completed=done,
                        failed=failed,
                        available=len(eligible),
                        latest=row["source_id"],
                    )
                ),
                flush=True,
            )
    (output / "summary.json").write_text(
        json.dumps(
            dict(
                members=len(coverage),
                available=len(eligible),
                completed=sum(r["status"] == "association_evaluated" for r in ledger.values()),
                failed=sum(r["status"] == "failed" for r in ledger.values()),
                position_estimates=0,
                sub_0_5km_target_verified=False,
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--latitude", type=float, required=True)
    parser.add_argument("--longitude", type=float, required=True)
    args = parser.parse_args()
    protected = Path("/mnt/qnap01")
    if args.output.resolve() == protected or protected in args.output.resolve().parents:
        parser.error("QNAP is read-only")
    if not 1 <= args.workers <= 4:
        parser.error("one to four bounded workers required")
    run(args.cohort.resolve(), args.output.resolve(), args.workers, args.latitude, args.longitude)
