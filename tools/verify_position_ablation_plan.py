#!/usr/bin/env python3
"""Exact SGP4 verification for every converged formal result in a sealed plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmark_position_subsets import atomic_write_result, read_json
from verify_formal_orbit import verify

from leo.analysis.research.regional_doppler import Region


def run(plan_path, results, output, prior, reranking):
    rows = []
    for job in read_json(plan_path)["jobs"]:
        if job["model"] == "legacy-strict-fixed-orbit":
            continue
        name = job["job_id"].removeprefix("sha256:") + ".json"
        path = results / name
        packet = read_json(path)
        if packet["result"]["status"] != "converged":
            continue
        target = output / name
        if target.exists():
            result = read_json(target)
        else:
            result = verify(
                Path(job["config"]["prepared_states_npz"]),
                path,
                prior,
                reranking,
                Region(**job["config"]["region"]),
                allow_unfitted_sources=True,
            )
            atomic_write_result(target, result)
        rows.append(
            {
                "job_id": job["job_id"],
                "model": job["model"],
                "passed": result["passed"],
                "rms_hz": result["rms_hz"],
                "maximum_absolute_hz": result["maximum_absolute_hz"],
            }
        )
    atomic_write_result(output / "summary.json", {"runs": rows})
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--results", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--prior", type=Path, required=True)
    p.add_argument("--reranking", type=Path, required=True)
    a = p.parse_args()
    run(a.plan, a.results, a.output, a.prior, a.reranking)
