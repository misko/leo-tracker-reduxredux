"""Robust truth-free A1 comparison with the frozen historical hard oracle."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import audit_receipts
import numpy as np
from compare_hard_oracle import _compare_fit, _digest, _load, _seed_key

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MANIFEST = ROOT / "plans/localization-approaches-2026-10-01/benchmark.json"
OLD_CONTINUATIONS = ROOT / "reports/2026_10_01_fixed_height_greedy/runs/t4-continuation"


def _sealed(path: Path) -> dict:
    receipt, failures = audit_receipts.read_sealed(path)
    if receipt is None or failures:
        raise ValueError(f"receipt seal failed: {path}: {failures}")
    return receipt


def _by_seed(fits) -> dict[tuple[float, float], dict]:
    result = {}
    for fit in fits:
        key = _seed_key(fit)
        if key in result:
            raise ValueError(f"duplicate exact seed coordinates: {key}")
        result[key] = fit
    return result


def _normalize_restart(fit: dict) -> dict:
    """Drop only the known duplicated restart-boundary objective sample."""
    result = dict(fit)
    objectives = list(fit.get("objectives", []))
    boundary = fit.get("_restart_boundary")
    if (
        isinstance(boundary, int)
        and 0 < boundary < len(objectives)
        and np.isclose(objectives[boundary - 1], objectives[boundary], rtol=0, atol=1e-10)
    ):
        del objectives[boundary]
    result["objectives"] = objectives
    return result


def _combine(parent: dict, child: dict, *, child_is_cumulative: bool) -> dict:
    result = dict(child)
    result["seed"] = parent["seed"]
    parent_objectives = list(parent.get("objectives", []))
    if child_is_cumulative:
        result["_restart_boundary"] = len(parent_objectives)
    else:
        result["iterations"] = int(parent.get("iterations", 0)) + int(
            child.get("iterations", 0)
        )
        result["objectives"] = parent_objectives + list(child.get("objectives", []))
        result["_restart_boundary"] = len(parent_objectives)
    result["stage"] = "continuation"
    return result


def _historical_final(primary_path: Path, binding: dict) -> dict[tuple[float, float], dict]:
    primary = _load(primary_path)
    final = _by_seed(dict(fit, stage="primary") for fit in primary.get("fits", []))
    continuation_path = OLD_CONTINUATIONS / f"{binding['unit_id']}-resume.json"
    if not continuation_path.is_file():
        return final
    continuation = _sealed(continuation_path)
    parent_binding = continuation.get("parent_binding") or {}
    bound_parent = ROOT / parent_binding.get("path", "")
    if bound_parent.resolve() != primary_path.resolve():
        raise ValueError(f"historical continuation parent path mismatch: {continuation_path}")
    if (
        parent_binding.get("sha256") != binding["sha256"]
        or _digest(bound_parent) != binding["sha256"]
    ):
        raise ValueError(f"historical continuation parent hash mismatch: {continuation_path}")
    parents = _by_seed(continuation.get("parent_fits", []))
    if set(parents) != set(final):
        raise ValueError(f"historical continuation parent fit set mismatch: {continuation_path}")
    for child in continuation.get("resumed_fits", []):
        key = _seed_key(child)
        if key not in parents:
            raise ValueError(f"historical resumed fit lacks exact parent seed: {key}")
        final[key] = _combine(parents[key], child, child_is_cumulative=False)
    return final


def _receipt_paths(folder: Path) -> dict[str, Path]:
    result = {}
    if not folder.is_dir():
        return result
    for path in sorted(folder.rglob("DS*.json")):
        if path.name.endswith((".launch.json", ".progress.json", ".seal.json")):
            continue
        receipt = _load(path)
        if receipt.get("config", {}).get("arm") != "A1":
            continue
        unit = receipt.get("unit_id")
        if unit in result:
            raise ValueError(f"duplicate official A1 receipt: {unit}")
        result[unit] = path
    return result


def _official_final(primary_path: Path, continuation_path: Path | None) -> tuple[dict, dict]:
    primary = _sealed(primary_path)
    primary_fits = _by_seed(dict(fit, stage="primary") for fit in primary.get("fits", []))
    if continuation_path is None:
        return primary, primary_fits
    continuation = _sealed(continuation_path)
    parent = continuation.get("parent") or {}
    if Path(parent.get("path", "")).resolve() != primary_path.resolve():
        raise ValueError(f"official continuation parent path mismatch: {continuation_path}")
    if parent.get("sha256") != _digest(primary_path):
        raise ValueError(f"official continuation parent hash mismatch: {continuation_path}")
    children = _by_seed(continuation.get("fits", []))
    final = dict(primary_fits)
    for key, child in children.items():
        if key not in primary_fits:
            raise ValueError(f"official continuation fit lacks parent seed: {key}")
        if child != primary_fits[key]:
            final[key] = _combine(primary_fits[key], child, child_is_cumulative=True)
    return continuation, final


def compare(
    official_root: Path,
    manifest_path: Path = MANIFEST,
    *,
    state_atol: float = 1e-5,
    objective_atol: float = 1e-5,
) -> dict:
    manifest = _load(manifest_path)
    primary_paths = _receipt_paths(official_root / "primary" / "A1")
    continuation_paths = _receipt_paths(official_root / "continuation" / "A1")
    rows, units = [], []
    for binding in manifest["historical_primary_receipts"]:
        unit = binding["unit_id"]
        historical_path = ROOT / binding["path"]
        if _digest(historical_path) != binding["sha256"]:
            raise ValueError(f"historical primary hash mismatch: {historical_path}")
        if unit not in primary_paths:
            units.append({"unit_id": unit, "comparability": "not_run", "compared_seed_count": 0})
            continue
        official_receipt, official = _official_final(
            primary_paths[unit], continuation_paths.get(unit)
        )
        if not official:
            status = official_receipt.get("status")
            exception = official_receipt.get("exception") or {}
            classification = (
                "acquisition_failed" if "acquisition" in str(exception.get("message", "")).lower()
                else "no_fit_endpoints"
            )
            units.append({"unit_id": unit, "comparability": classification,
                          "official_status": status, "compared_seed_count": 0})
            continue
        historical = _historical_final(historical_path, binding)
        common = sorted(set(official) & set(historical))
        missing_official = sorted(set(historical) - set(official))
        extra_official = sorted(set(official) - set(historical))
        for seed in common:
            rows.append(_compare_fit(
                unit, seed, _normalize_restart(official[seed]),
                _normalize_restart(historical[seed]), state_atol=state_atol,
                objective_atol=objective_atol,
            ))
        units.append({
            "unit_id": unit,
            "comparability": "compared" if common else "no_common_fit_seeds",
            "official_status": official_receipt.get("status"),
            "compared_seed_count": len(common),
            "historical_only_seeds": missing_official,
            "official_only_seeds": extra_official,
        })
    counts = Counter(row["classification"] for row in rows)
    unit_counts = Counter(unit["comparability"] for unit in units)
    return {
        "schema": "hard-oracle-comparison/v2",
        "qualification": (
            "truth-free numerical audit; exact seed joins; acquisition failures and "
            "different budget coverage are not numerical discrepancies"
        ),
        "planned_unit_denominator": 64,
        "unit_comparability_counts": dict(sorted(unit_counts.items())),
        "seed_classification_counts": dict(sorted(counts.items())),
        "units": units,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("official_root", type=Path)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare(args.official_root, args.manifest)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
