"""Seal all historical members and numerical sources; launch nothing."""

import datetime
import hashlib
import sys
from collections import Counter
from itertools import zip_longest
from pathlib import Path

import engine

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    destination = HERE / "protocol.json"
    assert not destination.exists()
    upstream = HERE.parent / "2026_10_09_position_error_iter87/protocol.json"
    old = engine.AUDIT["read"](upstream)
    files = {upstream}
    for name, expected in old["source_sha256"].items():
        path = ROOT / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
        files.add(path)
    groups = {
        dataset: [b for b in old["members"] if b["member"]["dataset"] == dataset]
        for dataset in ("DS16", "DS17", "DS18")
    }
    members = [b for row in zip_longest(*groups.values()) for b in row if b is not None]
    assert Counter(b["member"]["dataset"] for b in members) == dict(DS16=63, DS17=51, DS18=34)
    labels = [b["member"]["inventory_label"] for b in members]
    assert len(labels) == len(set(labels)) == 148
    for name in (
        "engine.py",
        "freeze.py",
        "README.md",
        "PREPARATION.md",
        "test_engine.py",
        "test_likelihood.py",
        "controller.py",
        "test_controller.py",
    ):
        files.add(HERE / name)
    for module in tuple(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if filename:
            path = Path(filename).resolve()
            if (
                path.is_file()
                and path.suffix in (".py", ".so")
                and (
                    path.is_relative_to(ROOT / "reports")
                    or path.is_relative_to(ROOT / "src/leo")
                    or "/worker/src/leo/" in str(path)
                )
            ):
                files.add(path)
    plan = dict(
        frozen_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        members=members,
        labels=labels,
        shards=2,
        widths_hz=list(engine.WIDTHS),
        arms=list(engine.ARMS),
        maximum_seconds=90,
        maximum_iterations=600,
        stationarity_threshold=0.001,
        archive_objective_tolerance=1e-6,
        maximum_fit_calls=592,
        decision_criteria=dict(
            comparison="100 operational versus matched125 operational; archive delta separate",
            pooled_mean_minimum_improvement_fraction=0.05,
            pooled_median_minimum_improvement_fraction=0.05,
            maximum_dataset_mean_regression_fraction=0.05,
            maximum_pooled_p95_and_worst_regression_fraction=0.10,
            paired_regression_threshold_km=1.0,
            paired_regression_count="No increase versus archive, candidate compared with control",
            failure="Retain125; no further width tuning on these outcomes",
        ),
        grouping="Full consumed census by dataset; no random groups or uncertainty claims",
        baseline="Immutable85 B7, reconstructed by immutable87; no selective recovered endpoints",
        starts="Shared archived fitted-B7 vector/clock; zero-c locks static/time RF",
        fallback="Unqualified100 -> qualified same-arm125 -> archivedB7; no cross-score ranking",
        evaluation="Inference only; references/errors are not accessed by this engine",
        scope="148 consumed development members; no reserve, RF or deployment",
        execution="At most two single-thread workers; append-only attempts and terminals",
        source_sha256={
            str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p): hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
            for p in sorted(files)
        },
    )
    engine.write(destination, plan)
    print("Frozen 106; no numerical evaluations or fits launched", flush=True)


if __name__ == "__main__":
    main()
