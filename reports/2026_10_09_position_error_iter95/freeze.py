"""Freeze calibration-to-B7 continuation after its prefit inventory is complete."""

import argparse
import datetime
import hashlib
from pathlib import Path

import continue_region

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PARENT = HERE.parent / "2026_10_09_position_error_iter93"


def main(polish_results, polish_fit_fields):
    assert not (HERE / "protocol.json").exists()
    old_path = PARENT / "prefit-protocol.json"
    old = continue_region.read(old_path)
    files = {ROOT / name for name in old["source_sha256"]}
    for name, expected in old["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    files.add(old_path)
    inventory = []
    for start in old["starts"]:
        for solver in old["solvers"]:
            path = PARENT / "prefit-attempts" / f"{start}-{solver}.json"
            row = continue_region.read(path)
            assert "fit" in row and "vector" in row["fit"]
            files.add(path)
            inventory.append(dict(path=str(path.relative_to(ROOT)), fit_fields=["fit"]))
    expected_parents = {ROOT / f"reports/2026_10_09_position_error_iter{i}" for i in (94, 96)}
    assert {path.resolve().parent for path in polish_results} == expected_parents
    assert len(polish_results) == 2
    for polish_result in polish_results:
        polish_result = polish_result.resolve()
        polished = continue_region.read(polish_result)
        for field in polish_fit_fields:
            polished = polished[field]
        assert all(field in polished for field in ("vector", "objective", "converged"))
        files.add(polish_result)
        files.update(polish_result.parent.glob("*.py"))
        files.update(polish_result.parent.glob("*protocol*.json"))
        inventory.append(
            dict(path=str(polish_result.relative_to(ROOT)), fit_fields=polish_fit_fields)
        )
    files.update(
        HERE / name
        for name in (
            "extract_ordinary_winner.py",
            "ordinary-winner-checkpoints.json",
            "continue_region.py",
            "test_continue_region.py",
            "freeze.py",
            "README.md",
        )
    )
    files.add(PARENT / "prefit-terminal-supplement.json")
    plan = dict(
        frozen_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        session_id=old["session_id"],
        prefit_inventory=inventory,
        stage_fit_seconds=20,
        stage_iterations=600,
        association_seconds=60,
        slice_seconds=500,
        maximum_slices=6,
        selection="Minimum same-model score among independently qualified ordinary prefits",
        starts="Association, zero-timing, own-continuation per arm; original priors",
        ranking="regional_winners objective+external calibration penalty; strict improvement",
        baseline="Ordinary-only B7 replay plus archived published B7 comparison",
        joint="Unmodified B7 stages90s/600; no cross-model downstream objective choice",
        bounds="Existing hard60 and25km disk; no threshold relaxation",
        scope="Consumed user-selected scan; no reference-guided hypothesis or new RF",
        source_sha256={
            str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted(files)
        },
    )
    continue_region.write(HERE / "protocol.json", plan)
    print("Frozen continuation; no position fit launched")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--polish-result", type=Path, required=True, action="append")
    parser.add_argument("--polish-fit-fields", nargs="*", default=[])
    args = parser.parse_args()
    main(args.polish_result, args.polish_fit_fields)
