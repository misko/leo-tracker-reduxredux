"""Prepare matched shape-preserving sparse packets, without target truth."""

from __future__ import annotations

import argparse
import math
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

from benchmark_position_subsets import _subset_metrics, atomic_write_result, file_hash, read_json

from leo.analysis.research.position_shape_subsets import shape_preserving_order
from leo.analysis.research.position_subsets import Observation, PositionSubset, canonical_hash


def prepare(source_plan, output, seeds=tuple(range(3)), formal_only=False):
    plan = read_json(source_plan)
    original = next(j for j in plan["jobs"] if j["model"] == "formal-orbit-correction-v6")
    manifest = read_json(Path(original["config"]["manifest_path"]))
    rows = tuple(Observation(**r) for r in manifest["observations"])
    by_id = {r.observation_id: r for r in rows}
    count = sum(r.fitting for r in rows)
    all_tracks = {r.track_id for r in rows if r.fitting}
    evaluation = tuple(sorted(r.observation_id for r in rows if not r.fitting))
    root = Path(__file__).parents[1]
    jobs = []
    for packet in (3, 5):
        for seed in seeds:
            order = shape_preserving_order(rows, seed=seed, packet_size=packet)
            for fraction in (1 / 32, 1 / 16, 1 / 8):
                ids = tuple(sorted(order[: math.floor(count * fraction)]))
                tracks = {by_id[i].track_id for i in ids}
                unsupported = tuple(i for i in evaluation if by_id[i].track_id not in tracks)
                subset = PositionSubset(
                    "density",
                    fraction,
                    seed,
                    ids,
                    evaluation,
                    unsupported,
                    tuple(sorted(all_tracks - tracks)),
                    f"shape-packet-{packet}-spanweighted-v1",
                )
                for label, settings in (
                    ("formal", {}),
                    (
                        "gaussian-fixed250",
                        {"gaussian_noise": True, "infer_measurement_sigma": False},
                    ),
                ):
                    if formal_only and label != "formal":
                        continue
                    job = deepcopy(original)
                    job.pop("job_id")
                    job.update(
                        model=f"shape{packet}-{label}",
                        model_config=settings,
                        subset=asdict(subset),
                        subset_id=subset.subset_id,
                        subset_aliases=[],
                        subset_metrics=_subset_metrics(subset, by_id, count),
                        numerical_source_hash=file_hash(
                            root / "src/leo/analysis/research/formal_orbit.py"
                        ),
                        sampling_source_hash=file_hash(
                            root / "src/leo/analysis/research/position_shape_subsets.py"
                        ),
                    )
                    job["job_id"] = canonical_hash(job)
                    jobs.append(job)
    result = {
        "schema": "position-subset-plan-v1",
        "jobs": jobs,
        "manifest_hash": manifest["manifest_hash"],
        "config_hash": canonical_hash(
            {"packets": [3, 5], "seeds": list(seeds), "formal_only": formal_only}
        ),
        "experiment": "metadata-only-shape-packets",
    }
    result["plan_hash"] = canonical_hash(result)
    atomic_write_result(output, result)
    print(len(jobs))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-plan", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--seed-count", type=int, default=3)
    p.add_argument("--formal-only", action="store_true")
    a = p.parse_args()
    if not 1 <= a.seed_count <= 20:
        p.error("seed-count must be between 1 and 20")
    prepare(a.source_plan, a.output, tuple(range(a.seed_count)), a.formal_only)
