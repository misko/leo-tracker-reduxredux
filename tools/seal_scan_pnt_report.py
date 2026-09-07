#!/usr/bin/env python3
"""Verify exported cohort accounting and record evidence hashes and test results."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    output = args.output
    inventory = json.loads((output / "inventory.json").read_text())
    summary = json.loads((output / "summary.json").read_text())
    result_paths = sorted((output / "results").glob("scan-hop-*.json"))
    results = [json.loads(path.read_text()) for path in result_paths]
    assert len(results) == len(inventory["scans"]) == summary["scan_count"] == 24
    assert sum(len(row["episodes"]) for row in results) == summary["episode_count"] == 502
    source_observations = 0
    for row in inventory["scans"]:
        assert row["included"] and row["qualified"]
        assert row["analyzed_visits"] == row["visit_count"]
        assert row["tle_collected_ns"] < row["reference_utc_ns"]
        payload = (output / "evidence" / row["tle_file"]).read_bytes()
        assert "sha256:" + hashlib.sha256(payload).hexdigest() == row["tle_digest"]
        source = json.loads((output / "evidence" / f"{row['session_id']}.json").read_text())
        ids = [candidate for series in source["series"] for candidate in series["candidate_ids"]]
        assert len(ids) == len(set(ids)), "primary tracklets must not reuse source candidates"
        source_observations += len(ids)
    for target in re.findall(r"\]\(([^)]+)\)", args.report.read_text()):
        if not target.startswith("https://") and not target.endswith("evidence-seal.json"):
            assert (args.report.parent / target).exists(), f"missing report link: {target}"
    png_paths = list(output.rglob("*.png"))
    assert len(png_paths) == 37
    for path in png_paths:
        assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    tests = [
        "tests/analysis/test_scan_pnt_experiment.py",
        "tests/analysis/test_persistent_hop_trajectory.py",
        "tests/analysis/test_persistent_hop_tle_match.py",
        "tests/application/test_persistent_hop_trajectory.py",
    ]
    test_command = [sys.executable, "-m", "pytest", "-q", *tests]
    tested = subprocess.run(test_command, capture_output=True, text=True, check=True)
    code_paths = [
        Path("src/leo/analysis/research/scan_pnt_experiment.py"),
        Path("tools/explore_scan_edge_joins.py"),
        Path("tools/report_eight_hour_scan_pnt.py"),
        Path("tools/evaluate_scan_pnt_cohort.py"),
        Path("tools/evaluate_scan_pnt_longitudinal.py"),
        Path("tools/plot_scan_pnt_cohort.py"),
        Path("tools/plot_scan_pnt_handoff.py"),
        Path(__file__).resolve(),
        Path(tests[0]),
        args.report,
    ]
    manifest = {
        "schema_version": 1,
        "created_utc": datetime.now(UTC).isoformat(),
        "python_version": sys.version,
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "sgp4", "matplotlib", "pydantic", "pytest")
        },
        "checks": {
            "scans": len(results),
            "episodes": 502,
            "pngs": len(png_paths),
            "source_observations": source_observations,
            "causal_snapshot_digests_verified": True,
            "report_links_verified": True,
            "source_candidates_disjoint": True,
        },
        "test_command": test_command,
        "test_output": tested.stdout,
        "files": [
            {
                "path": str(path.resolve().relative_to(Path.cwd())),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in sorted(
                set(
                    code_paths
                    + [
                        p
                        for p in output.rglob("*")
                        if p.is_file() and p.name != "evidence-seal.json"
                    ]
                )
            )
        ],
    }
    (output / "evidence-seal.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(tested.stdout)
    print(json.dumps(manifest["checks"]))


if __name__ == "__main__":
    main()
