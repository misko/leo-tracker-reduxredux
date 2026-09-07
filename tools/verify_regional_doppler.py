#!/usr/bin/env python3
"""Verify sealed regional evidence, report assets and numerical regression tests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_run_files(run, seal, *, published_only=False):
    """Missing intermediates require explicit compact-publication verification."""
    omitted = []
    for name, expected in seal.items():
        path = run / name
        if not path.exists() and published_only and re.fullmatch(r"scan-hop-[a-f0-9]+\.npz", name):
            omitted.append(name)
        else:
            assert sha(path) == expected, (run.name, name)
    return omitted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--published-only",
        action="store_true",
        help="Explicitly permit omitted per-scan NPZ intermediates in a compact checkout",
    )
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    root = repo / "reports/figures/2026_09_07_blind_regional_pnt"
    evaluation = json.loads((root / "evaluation-expanded.json").read_text())
    assert len(evaluation["runs"]) == 22
    assert len(evaluation["polishes"]) == 20
    omitted = {}
    evidence = repo / "reports/figures/2026_09_07_eight_hour_scan_pnt"
    checked_inputs = {}
    proposals = {"sha256:" + sha(p): p for p in root.glob("*-points.json")}

    def check_input(path, expected):
        if path not in checked_inputs:
            checked_inputs[path] = "sha256:" + sha(path)
        assert checked_inputs[path] == expected, path

    for row in evaluation["runs"]:
        run = root / row["run"]
        seal = run / "evaluation-seal.json"
        assert sha(seal) == row["seal_digest"]
        missing = verify_run_files(
            run, json.loads(seal.read_text()), published_only=args.published_only
        )
        if missing:
            omitted[run.name] = missing
        result = json.loads((run / "result.json").read_text())
        assert result["complete"] and not result["position_truth_used"]
        assert result["scan_count"] == 24 and result["episode_count"] == 502
        check_input(evidence / "inventory.json", result["inventory_digest"])
        if result["points_digest"]:
            proposal = json.loads(proposals[result["points_digest"]].read_text())
            assert not proposal["heldout_values_or_truth_used"]
            check_input(
                root / proposal["parent_run"] / "accumulated.npz", proposal["training_map_digest"]
            )
        for scan in json.loads((run / "history.json").read_text()):
            source = evidence / "evidence" / f"{scan['session_id']}.json"
            check_input(source, scan["source_digest"])
            metadata = json.loads(source.read_text())["inventory"]
            assert metadata["tle_collected_ns"] < metadata["reference_utc_ns"] - 5_000_000_000
            check_input(source.parent / metadata["tle_file"], scan["tle_digest"])
    for name, expected in json.loads(
        (root / "evaluation-expanded.inference-seal.json").read_text()
    ).items():
        assert sha(repo / name) == expected, name
    for row in evaluation["polishes"]:
        assert row["converged"]
        assert max(abs(t) for t in row["orbit_times_s"]) <= 2
    figures = sorted(root.glob("*.png"))
    assert len(figures) == 13
    map_source = json.loads((root / "map-source.json").read_text())
    assert sha(root / map_source["file"]) == map_source["sha256"]
    report = repo / "reports/2026_09_07_blind_regional_doppler_positioning.md"
    for target in re.findall(r"\]\(([^)]+)\)", report.read_text()):
        if not target.startswith("https://"):
            assert (report.parent / target).exists(), target
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/analysis/test_regional_doppler.py",
        "tests/analysis/test_scan_pnt_experiment.py",
        "tests/analysis/test_blinded_doppler_position.py",
        "tests/analysis/test_blinded_position_evaluation.py",
        "tests/sky",
    ]
    completed = subprocess.run(
        command,
        cwd=repo,
        env={**os.environ, "PYTHONPATH": "src", "OPENBLAS_NUM_THREADS": "1"},
        text=True,
        capture_output=True,
        check=True,
    )
    sources = [
        repo / "src/leo/analysis/research/regional_doppler.py",
        repo / "tests/analysis/test_regional_doppler.py",
        report,
        *figures,
    ]
    sources.extend(
        repo / "tools" / name
        for name in (
            "replay_regional_doppler.py",
            "refine_regional_grid.py",
            "polish_regional_doppler.py",
            "evaluate_regional_doppler.py",
            "plot_regional_doppler.py",
            "plot_continental_doppler.py",
            "verify_regional_doppler.py",
        )
    )
    receipt = {
        "complete": True,
        "verification_scope": "published_only"
        if args.published_only
        else "all_local_intermediates",
        "omitted_intermediates": omitted,
        "sealed_runs_verified": len(evaluation["runs"]),
        "sealed_local_fits_verified": len(evaluation["polishes"]),
        "png_count": len(figures),
        "tests": {
            "command": command,
            "exit_code": completed.returncode,
            "output": completed.stdout,
        },
        "files": {str(p.relative_to(repo)): sha(p) for p in sources},
        "inputs": {str(p.relative_to(repo)): digest for p, digest in checked_inputs.items()},
    }
    receipt_name = "verification-published.json" if args.published_only else "verification.json"
    (root / receipt_name).write_text(json.dumps(receipt, indent=2) + "\n")
    print(completed.stdout)
    print(
        f"Verified {len(evaluation['runs'])} sealed replays, "
        f"{len(evaluation['polishes'])} local fits, {len(figures)} PNGs "
        "and all local report links. "
        f"Explicitly omitted {sum(map(len, omitted.values()))} unpublished intermediate arrays."
    )


if __name__ == "__main__":
    main()
