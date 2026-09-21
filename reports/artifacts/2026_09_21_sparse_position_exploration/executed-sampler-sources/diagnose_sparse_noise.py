"""Freeze sparse-noise diagnostics using existing memberships and priors.

These are training-only fixed-identity experiments. No target coordinate,
full-data fitted noise estimate, or full-data optimizer state is an input.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path

from benchmark_position_subsets import atomic_write_result, file_hash, read_json

from leo.analysis.research.position_subsets import canonical_hash


VARIANTS = {
    "sparse-student-fixed250": {"infer_measurement_sigma": False},
    "sparse-gaussian-fixed250": {"infer_measurement_sigma": False, "gaussian_noise": True},
    "sparse-gaussian-learned": {"gaussian_noise": True},
}


def prepare(source_plan, output):
    plan = read_json(source_plan)
    selected = [j for j in plan["jobs"] if j["model"] == "formal-orbit-correction-v6"
                and j["subset"]["method"] == "density" and j["subset"]["seed"] in (0, 1, 2)]
    jobs = []
    core = Path(__file__).parents[1] / "src/leo/analysis/research/formal_orbit.py"
    for variant, settings in VARIANTS.items():
        for original in selected:
            job = deepcopy(original)
            job.pop("job_id")
            job["model"] = variant
            job["model_config"] = settings
            job["numerical_source_hash"] = file_hash(core)
            job["job_id"] = canonical_hash(job)
            jobs.append(job)
    result = {"schema": "position-subset-plan-v1", "jobs": jobs,
              "manifest_hash": plan["manifest_hash"],
              "experiment": "three-prespecified-noise-variants-three-seeds-frozen-memberships",
              "config_hash": canonical_hash(VARIANTS)}
    result["plan_hash"] = canonical_hash(result)
    atomic_write_result(output, result)
    print(len(jobs))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.source_plan, args.output)
