"""Freeze the reviewed pilot only when explicitly executed by the parent."""

import datetime
import hashlib
import json
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def build_plan(authority, selected, ranks, sources, seed):
    potential = authority["members"]
    assert len(potential) == 148 and len(selected) == 12
    assert len({b["member"]["session_id"] for b in potential}) == 148
    for dataset, total in (("DS16", 63), ("DS17", 51), ("DS18", 34)):
        assert sum(b["member"]["dataset"] == dataset for b in potential) == total
        assert sum(b["member"]["dataset"] == dataset for b in selected) == 4
    assert all(b in potential for b in selected)
    assert len({b["member"]["session_id"] for b in selected}) == 12
    assert len(ranks) == 148
    assert {r["label"] for r in ranks if r["selected"]} == {
        b["member"]["inventory_label"] for b in selected
    }
    return dict(
        potential_members=potential,
        members=selected,
        selection_ranks=ranks,
        selection_seed=seed,
        source_sha256=sources,
        rhos=[0.0, 0.5],
        sigma_hz=125,
        maximum_seconds=90,
        maximum_iterations=600,
        stationarity_threshold=0.001,
        maximum_workers=2,
        threads_per_worker=1,
        matched_start="Shared archived fitted-B7 vector/clock; zero-c static and last2RF locks",
        raw_attempts_expected=48,
        progression_gates=dict(
            all_48_raw_independently_qualified=True,
            fitted_mean_improvement_fraction_minimum=0.05,
            fitted_median_nonworse=True,
            both_arms_maximum_paired_regression_km=1,
            both_arms_worst_nonworse=True,
            zero_c_mean_maximum_worsening_fraction=0.05,
            absolute_fit_budget_seconds=90,
        ),
        scope="Consumed conditional pilot; no sequence-score selection or validation claim",
        reference_scope="Evaluation only, except inherited artifact provenance admission checks",
        fallback="Explicit rho0 then archivedB7; fallback never satisfies raw progression gate",
    )


def prepare():
    path = HERE.parent / "2026_10_09_position_error_iter108/protocol.json"
    authority = json.loads(path.read_text())
    sources = dict(authority["source_sha256"])
    for name, expected in sources.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    sources[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    for directory in (HERE.parent / "2026_10_09_position_error_iter109", HERE):
        for file in sorted(directory.iterdir()):
            if file.is_file() and file.suffix in (".py", ".md"):
                sources[str(file.relative_to(ROOT))] = hashlib.sha256(file.read_bytes()).hexdigest()
    engine = runpy.run_path(str(HERE / "engine.py"))
    selected, ranks = engine["select_members"](authority["members"], engine["SEED"])
    plan = build_plan(authority, selected, ranks, sources, engine["SEED"])
    plan["frozen_utc"] = datetime.datetime.now(datetime.UTC).isoformat()
    return plan


def main():
    plan = prepare()
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(plan, stream, indent=2)
        stream.write("\n")
    print("Pilot selected and frozen; no recording evaluated")


if __name__ == "__main__":
    main()
