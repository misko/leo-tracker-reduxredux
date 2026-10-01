"""Compare A1 endpoints with the frozen hard-association numerical oracle.

This diagnostic joins fits by exact acquisition seed coordinates.  It never
loads reference locations and distinguishes numerical discrepancies from runs
that simply reached different iteration or continuation coverage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEFAULT_MANIFEST = ROOT / "plans/localization-approaches-2026-10-01/benchmark.json"
HISTORICAL_CONTINUATIONS = ROOT / "reports/2026_10_01_fixed_height_greedy/runs/t4-continuation"


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"receipt is not an object: {path}")
    return value


def _seed_key(fit: dict) -> tuple[float, float]:
    seed = fit.get("seed") or fit.get("parent_seed")
    if not isinstance(seed, dict):
        raise ValueError("fit lacks an acquisition seed")
    return float(seed["east_km"]), float(seed["north_km"])


def _fits_by_seed(fits: list[dict]) -> dict[tuple[float, float], dict]:
    result = {}
    for fit in fits:
        key = _seed_key(fit)
        if key in result:
            raise ValueError(f"duplicate exact seed coordinates: {key}")
        result[key] = fit
    return result


def _continuation_fit(parent: dict, resumed: dict) -> dict:
    combined = dict(resumed)
    combined["seed"] = parent["seed"]
    combined["iterations"] = int(parent.get("iterations", 0)) + int(
        resumed.get("iterations", 0)
    )
    parent_objectives = list(parent.get("objectives", []))
    resumed_objectives = list(resumed.get("objectives", []))
    if parent_objectives and resumed_objectives and np.isclose(
        parent_objectives[-1], resumed_objectives[0], rtol=0, atol=1e-10
    ):
        resumed_objectives = resumed_objectives[1:]
    combined["objectives"] = parent_objectives + resumed_objectives
    combined["stage"] = "continuation"
    return combined


def _historical_fits(primary: dict, continuation: dict | None) -> list[dict]:
    fits = [dict(fit, stage="primary") for fit in primary.get("fits", [])]
    if continuation is None:
        return fits
    parents = continuation.get("parent_fits", [])
    resumed = continuation.get("resumed_fits", [])
    if len(parents) != len(resumed):
        raise ValueError("historical continuation parent/resumed fit count differs")
    continued = {
        _seed_key(parent): _continuation_fit(parent, child)
        for parent, child in zip(parents, resumed, strict=True)
    }
    return [continued.get(_seed_key(fit), fit) for fit in fits]


def _official_receipts(root: Path) -> dict[str, Path]:
    result = {}
    for path in sorted(root.rglob("DS*.json")):
        if path.name.endswith((".launch.json", ".progress.json", ".seal.json")):
            continue
        receipt = _load(path)
        if receipt.get("config", {}).get("arm") != "A1":
            continue
        unit = receipt.get("unit_id")
        if unit in result:
            raise ValueError(f"duplicate official A1 receipt for {unit}")
        result[unit] = path
    return result


def _state(fit: dict) -> np.ndarray:
    return np.asarray(fit.get("mean", []) + fit.get("satellite_epoch_s", []), dtype=float)


def _compare_fit(
    unit: str,
    seed: tuple[float, float],
    official: dict,
    historical: dict,
    *,
    state_atol: float,
    objective_atol: float,
) -> dict:
    current_state, old_state = _state(official), _state(historical)
    if current_state.shape != old_state.shape or current_state.ndim != 1:
        raise ValueError(f"state shape mismatch for {unit} seed {seed}")
    current_objectives = np.asarray(official.get("objectives", []), dtype=float)
    old_objectives = np.asarray(historical.get("objectives", []), dtype=float)
    shared = min(current_objectives.size, old_objectives.size)
    prefix_delta = (
        float(np.max(np.abs(current_objectives[:shared] - old_objectives[:shared])))
        if shared else None
    )
    endpoint_objective_delta = (
        float(current_objectives[-1] - old_objectives[-1])
        if current_objectives.size and old_objectives.size else None
    )
    current_iterations = int(official.get("iterations", 0))
    old_iterations = int(historical.get("iterations", 0))
    iterations_equal = current_iterations == old_iterations
    both_converged = bool(official.get("converged")) and bool(historical.get("converged"))
    comparable_endpoint = iterations_equal or both_converged
    state_max = float(np.max(np.abs(current_state - old_state)))
    spatial_delta = float(np.linalg.norm(current_state[:2] - old_state[:2]))
    associations_equal = official.get("associations") == historical.get("associations")
    prefix_equivalent = prefix_delta is not None and prefix_delta <= objective_atol
    endpoint_equivalent = bool(
        comparable_endpoint
        and state_max <= state_atol
        and endpoint_objective_delta is not None
        and abs(endpoint_objective_delta) <= objective_atol
        and associations_equal
    )
    if endpoint_equivalent:
        classification = "equivalent_endpoint"
    elif comparable_endpoint:
        classification = "numerical_discrepancy"
    elif prefix_equivalent:
        classification = "different_budget_coverage"
    else:
        classification = "diverged_before_budget_boundary"
    return {
        "unit_id": unit,
        "seed_east_km": seed[0],
        "seed_north_km": seed[1],
        "official_stage": official.get("stage", "primary"),
        "historical_stage": historical.get("stage", "primary"),
        "official_iterations": current_iterations,
        "historical_iterations": old_iterations,
        "iterations_equal": iterations_equal,
        "official_converged": bool(official.get("converged")),
        "historical_converged": bool(historical.get("converged")),
        "official_reason": official.get("reason"),
        "historical_reason": historical.get("reason"),
        "shared_objective_count": shared,
        "objective_prefix_max_abs_delta": prefix_delta,
        "endpoint_objective_delta": endpoint_objective_delta,
        "state_max_abs_delta": state_max,
        "spatial_endpoint_delta_km": spatial_delta,
        "associations_equal": associations_equal,
        "classification": classification,
    }


def compare(
    official_root: Path,
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    official_continuation_root: Path | None = None,
    state_atol: float = 1e-5,
    objective_atol: float = 1e-5,
) -> dict:
    """Return truth-free per-seed numerical equivalence diagnostics."""
    manifest = _load(manifest_path)
    official_paths = _official_receipts(official_root)
    continuation_paths = (
        _official_receipts(official_continuation_root)
        if official_continuation_root is not None else {}
    )
    rows = []
    missing = []
    for binding in manifest.get("historical_primary_receipts", []):
        unit = binding["unit_id"]
        if unit not in official_paths:
            missing.append(unit)
            continue
        historical_path = ROOT / binding["path"]
        if _digest(historical_path) != binding["sha256"]:
            raise ValueError(f"historical receipt digest mismatch: {historical_path}")
        historical_primary = _load(historical_path)
        historical_continuation_path = HISTORICAL_CONTINUATIONS / f"{unit}-resume.json"
        historical_continuation = (
            _load(historical_continuation_path)
            if historical_continuation_path.is_file() else None
        )
        historical = _fits_by_seed(
            _historical_fits(historical_primary, historical_continuation)
        )
        official_receipt = _load(official_paths[unit])
        official_fits = [dict(fit, stage="primary") for fit in official_receipt.get("fits", [])]
        if unit in continuation_paths:
            continued_receipt = _load(continuation_paths[unit])
            official_fits = [
                dict(fit, stage="continuation")
                for fit in continued_receipt.get("fits", [])
            ]
        current = _fits_by_seed(official_fits)
        if set(current) != set(historical):
            raise ValueError(f"exact acquisition seed set mismatch for {unit}")
        rows.extend(
            _compare_fit(
                unit, seed, current[seed], historical[seed],
                state_atol=state_atol, objective_atol=objective_atol,
            )
            for seed in current
        )
    counts = Counter(row["classification"] for row in rows)
    return {
        "schema": "hard-oracle-comparison/v1",
        "qualification": (
            "truth-free numerical diagnostic; exact seed-coordinate join; "
            "different iteration coverage is not a status-equivalence failure"
        ),
        "official_root": str(official_root.resolve()),
        "official_continuation_root": (
            None if official_continuation_root is None
            else str(official_continuation_root.resolve())
        ),
        "state_atol": state_atol,
        "objective_atol": objective_atol,
        "completed_units": len({row["unit_id"] for row in rows}),
        "missing_units": missing,
        "classification_counts": dict(sorted(counts.items())),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("official_root", type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--official-continuation-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare(
        args.official_root, args.manifest,
        official_continuation_root=args.official_continuation_root,
    )
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(text, end="")
    else:
        args.output.write_text(text)


if __name__ == "__main__":
    main()
