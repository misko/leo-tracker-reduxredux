#!/usr/bin/env python3
"""Build a fail-closed DS1-versus-DS3 all-method comparison report.

Inference is never performed here.  This reader ingests only a sealed paired
matrix and sealed DS3 accounting artifacts.  It records unavailable values as
null and refuses the ``publish`` action until no required DS3 row is `not_run`
or otherwise nonterminal.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEFAULT_MATRIX = (
    ROOT / "reports/2026_09_25_ds3_all_iterations_backfill/paired-completion-matrix-v4.json"
)
DEFAULT_REGISTRY = HERE / "method-registry.json"
DS1_SUPERSEDING_AUDITS = {
    # I19's sealed corrected-bound audit explicitly rejects I15's former
    # qualification.  This is a scientific override, not a generic heuristic.
    15: ROOT / "reports/2026_09_25_ds1_iteration19_rate_bound_audit/comparison.json",
}
TERMINAL = {
    "qualified",
    "unqualified_boundary",
    "unqualified_numerical",
    "unqualified_parent",
    "unqualified_convergence",
    "no_position_diagnostic",
    "not_portable_legacy",
    "missing_historical_artifact",
    "unqualified_preflight",
    "terminal_control",
    "superseded_no_replay",
}
NONTERMINAL = {
    "not_run",
    "not_run_diagnostic",
    "missing_required_arm",
    "unsealed_artifact",
}


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def sidecar_matches(path: Path, actual: str) -> bool:
    if not path.is_file():
        return False
    words = path.read_text().strip().split(maxsplit=1)
    return bool(words) and words[0].removeprefix("sha256:") == actual


def verify(path: Path) -> dict[str, Any]:
    actual = digest(path).removeprefix("sha256:")
    sidecars = (path.with_suffix(path.suffix + ".sha256"), path.with_suffix(".sha256"))
    if not any(sidecar_matches(item, actual) for item in sidecars):
        raise ValueError(f"unsealed artifact: {path}")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = canonical(value)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(text.encode()).hexdigest() + "\n"
    )


def abs_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def point(value: dict[str, Any]) -> dict[str, float] | None:
    for key in ("estimated_position", "winner", "position", "selected_position"):
        row = value.get(key)
        if isinstance(row, dict) and {"latitude_deg", "longitude_deg"} <= set(row):
            return {
                "latitude_deg": float(row["latitude_deg"]),
                "longitude_deg": float(row["longitude_deg"]),
            }
    return None


def estimates(value: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return every explicitly reported position, preserving method labels.

    A boundary-qualified result can still contain one or more estimates.  Those
    values are useful diagnostic evidence, but callers must use the terminal
    status to decide whether they are eligible for a performance ranking.
    """
    if not value:
        return []
    result: list[dict[str, Any]] = []
    direct = point(value)
    if direct is not None:
        result.append({"label": "selected", **direct})
    raw = value.get("estimated_positions")
    if isinstance(raw, list):
        for index, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            candidate = point({"estimated_position": item})
            if candidate is None:
                continue
            label = item.get("label", item.get("method", f"estimate-{index + 1}"))
            result.append({"label": str(label), **candidate})
    # A result sometimes repeats its selected point in estimated_positions.
    unique: dict[tuple[str, float, float], dict[str, Any]] = {}
    for item in result:
        unique[(item["label"], item["latitude_deg"], item["longitude_deg"])] = item
    return list(unique.values())


def first_number(value: Any, names: tuple[str, ...]) -> float | None:
    if isinstance(value, dict):
        for name in names:
            candidate = value.get(name)
            if isinstance(candidate, (int, float)) and math.isfinite(candidate):
                return float(candidate)
        for child in value.values():
            found = first_number(child, names)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = first_number(child, names)
            if found is not None:
                return found
    return None


def postseal_from_report(report_dir: str | None) -> dict[str, Any]:
    if not report_dir:
        return {
            "estimate": None,
            "postseal_error_km": None,
            "artifact": None,
            "artifact_sha256": None,
        }
    root = abs_path(report_dir)
    candidates = sorted(root.rglob("*postseal*.json"))
    for path in candidates:
        try:
            value = verify(path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        error = first_number(value, ("final_error_km", "postseal_error_km"))
        candidate = point(value)
        if candidate is None and isinstance(value.get("rows"), list) and value["rows"]:
            candidate = point(value["rows"][0])
        if error is not None or candidate is not None:
            return {
                "estimate": candidate,
                "postseal_error_km": error,
                "artifact": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                "artifact_sha256": digest(path),
            }
    return {
        "estimate": None,
        "postseal_error_km": None,
        "artifact": None,
        "artifact_sha256": None,
    }


def unqualified_reason(value: dict[str, Any]) -> str:
    """Make a sealed negative qualification legible without inferring a cause."""
    for key in ("failure_reason", "reason", "conclusion"):
        item = value.get(key)
        if isinstance(item, str) and item:
            return item
    if value.get("complete") is False:
        return "sealed inference is incomplete"
    for key in ("geographic_interior", "interior_closure"):
        if value.get(key) is False:
            return f"sealed {key} gate failed"
    gate = value.get("gate")
    if isinstance(gate, dict) and gate.get("passed") is False:
        failed = [name for name, passed in gate.get("criteria", {}).items() if passed is False]
        return "sealed gate failed" + (": " + ", ".join(failed) if failed else "")
    return "sealed qualification reports qualified=false"


def ds1_qualification(report_dir: str | None, iteration: int | None) -> dict[str, Any]:
    """Resolve DS1 eligibility from sealed qualification material only."""
    audit_path = DS1_SUPERSEDING_AUDITS.get(iteration)
    if audit_path is not None:
        audit = verify(audit_path)
        conclusion = audit.get("conclusion")
        if not isinstance(conclusion, str) or "unqualified" not in conclusion:
            raise ValueError(f"invalid superseding DS1 audit: {audit_path}")
        return {
            "status": "invalidated_by_later_audit",
            "ranking_eligible": False,
            "reason": conclusion,
            "artifact": str(audit_path.relative_to(ROOT)),
            "artifact_sha256": digest(audit_path),
        }
    if not report_dir:
        return {
            "status": "unavailable",
            "ranking_eligible": False,
            "reason": "no DS1 report directory",
            "artifact": None,
            "artifact_sha256": None,
        }
    root = abs_path(report_dir)
    # Qualification records take precedence. I14 predates a separate
    # qualification record, so its sealed inference carries the boolean.
    candidates = [root / "qualification.json", root / "inference.json", root / "stencil.json"]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            value = verify(path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        qualified = value.get("qualified")
        if isinstance(qualified, bool):
            return {
                "status": "qualified" if qualified else "unqualified",
                "ranking_eligible": qualified,
                "reason": "sealed qualification passed" if qualified else unqualified_reason(value),
                "artifact": str(path.relative_to(ROOT)),
                "artifact_sha256": digest(path),
            }
        gate = value.get("gate")
        if isinstance(gate, dict) and isinstance(gate.get("passed"), bool):
            passed = gate["passed"]
            return {
                "status": "qualified" if passed else "unqualified",
                "ranking_eligible": passed,
                "reason": "sealed gate passed" if passed else unqualified_reason(value),
                "artifact": str(path.relative_to(ROOT)),
                "artifact_sha256": digest(path),
            }
    return {
        "status": "unavailable",
        "ranking_eligible": False,
        "reason": "no sealed DS1 qualification artifact",
        "artifact": None,
        "artifact_sha256": None,
    }


def ds3_artifact(
    row: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None, str | None, str | None]:
    binding = row.get("artifact")
    if not isinstance(binding, dict) or not isinstance(binding.get("path"), str):
        return None, None, None, "missing artifact binding"
    path = abs_path(binding["path"])
    if not path.is_file():
        return None, str(path), None, "artifact path is missing"
    try:
        value = verify(path)
        if binding.get("sha256") and digest(path) != binding["sha256"]:
            raise ValueError("paired matrix artifact digest mismatch")
    except ValueError as error:
        return None, str(path), None, str(error)
    return (
        value,
        str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        digest(path),
        None,
    )


def load_method_registry(path: Path, matrix_sha256: str) -> tuple[dict[str, Any], str]:
    """Load the sealed method identity layer and bind it to the iteration ledger."""
    registry = verify(path)
    if registry.get("schema") != "ds1-ds3-method-registry/v1":
        raise ValueError("invalid method registry schema")
    ledger = registry.get("iteration_ledger")
    if not isinstance(ledger, dict) or ledger.get("sha256") != matrix_sha256:
        raise ValueError("method registry was built for a different iteration ledger")
    methods = registry.get("methods")
    if not isinstance(methods, list) or not methods:
        raise ValueError("method registry has no methods")
    ids = [row.get("method_id") for row in methods if isinstance(row, dict)]
    if len(ids) != len(methods) or any(not isinstance(item, str) for item in ids):
        raise ValueError("invalid method registry row")
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate method_id in method registry")
    if any(row.get("required_for_publication") is not True for row in methods):
        raise ValueError("all registry rows must state their publication requirement")
    return registry, digest(path)


def selected_model(value: dict[str, Any], selector: dict[str, Any] | None) -> dict[str, Any]:
    """Project a named model from a sealed multi-model artifact."""
    if not selector:
        return value
    model_id = selector.get("model_id")
    if not isinstance(model_id, str):
        raise ValueError("unsupported method artifact selector")
    models = value.get("models")
    if not isinstance(models, list):
        raise ValueError(f"artifact has no models for selector {model_id}")
    matches = [row for row in models if isinstance(row, dict) and row.get("model_id") == model_id]
    if len(matches) != 1:
        raise ValueError(f"selector {model_id} did not resolve exactly one model")
    model = matches[0]
    joint = model.get("joint_five")
    if not isinstance(joint, dict):
        raise ValueError(f"selector {model_id} has no joint_five result")
    position = joint.get("position")
    result = {
        "estimated_position": position if isinstance(position, dict) else None,
        "objective": joint.get("objective"),
        "support": joint.get("support"),
        "qualified": model.get("qualification") == "qualified",
        "reason": model.get("qualification_reason"),
        "selected_model_id": model_id,
    }
    return result


def resolve_ds3_method(
    method: dict[str, Any], iteration_rows: dict[int, dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any] | None, str | None, str | None, str | None]:
    """Resolve one method arm without treating its integer iteration as identity."""
    binding = method.get("ds3_binding")
    if not isinstance(binding, dict):
        raise ValueError(f"method {method.get('method_id')} has no DS3 binding")
    kind = binding.get("kind")
    if kind == "pending":
        row = {
            "status": "not_run",
            "is_terminal": False,
            "artifact": None,
            "reason": binding.get("reason"),
        }
        return row, None, None, None, None
    if kind == "accounting":
        status = str(binding.get("terminal_status"))
        if status not in TERMINAL:
            raise ValueError(f"nonterminal accounting status for {method.get('method_id')}")
        row = {
            "status": status,
            "is_terminal": True,
            "artifact": None,
            "reason": binding.get("reason"),
        }
        return row, None, None, None, None
    if kind == "artifact":
        row = {
            "status": str(binding.get("terminal_status")),
            "is_terminal": str(binding.get("terminal_status")) in TERMINAL,
            "artifact": binding.get("artifact"),
        }
        value, path, sha256, error = ds3_artifact(row)
        if error:
            return row, None, path, sha256, error
        try:
            value = selected_model(value or {}, binding.get("selector"))
        except ValueError as exc:
            return row, None, path, sha256, str(exc)
        if row["status"] == "qualified" and value.get("qualified") is False:
            return row, value, path, sha256, "selected artifact model is not qualified"
        return row, value, path, sha256, None
    if kind != "iteration":
        raise ValueError(f"unsupported DS3 binding kind: {kind}")
    number = binding.get("iteration")
    if not isinstance(number, int) or number not in iteration_rows:
        raise ValueError(f"unknown iteration binding: {number}")
    paired = iteration_rows[number]
    row = dict(paired["ds3"])
    value, path, sha256, error = ds3_artifact(row)
    if error:
        return row, None, path, sha256, error
    if binding.get("require_ds3_execution") is True and (
        not isinstance(value, dict) or value.get("ds3_diagnostic_executed") is not True
    ):
        row.update(
            {
                "status": "not_run_diagnostic",
                "is_terminal": False,
                "reason": "DS3 diagnostic accounting exists but execution is false",
            }
        )
    label = binding.get("estimate_label")
    if isinstance(label, str) and row.get("is_terminal"):
        labels = {item["label"] for item in estimates(value)}
        if label not in labels:
            row.update(
                {
                    "status": "missing_required_arm",
                    "is_terminal": False,
                    "reason": f"terminal artifact has no estimate label {label}",
                }
            )
    return row, value, path, sha256, None


def arm_estimates(value: dict[str, Any] | None, binding: dict[str, Any]) -> list[dict[str, Any]]:
    result = estimates(value)
    label = binding.get("estimate_label")
    if isinstance(label, str):
        return [row for row in result if row["label"] == label]
    return result


def support(value: dict[str, Any] | None) -> dict[str, int | None]:
    if not value:
        return {"tracks": None, "observations": None, "sources": None}
    for key in ("support", "qualified_track_count", "full_observation_count"):
        row = value.get(key)
        if isinstance(row, dict):
            return {
                "tracks": row.get("tracks", row.get("track_count")),
                "observations": row.get("observations", row.get("observation_count")),
                "sources": row.get("sources", row.get("source_count")),
            }
    return {
        "tracks": value.get("qualified_track_count"),
        "observations": value.get("full_observation_count"),
        "sources": value.get("source_count"),
    }


def objective(value: dict[str, Any] | None) -> float | None:
    if not value:
        return None
    return first_number(
        value, ("objective", "balanced_exact_capped_loss", "selection_objective", "rf_objective")
    )


def runtime(value: dict[str, Any] | None) -> float | None:
    return first_number(value, ("elapsed_s", "wall_seconds")) if value else None


def method_name(iteration: int, ds1: dict[str, Any], ds3_value: dict[str, Any] | None) -> str:
    if ds3_value and isinstance(ds3_value.get("historical_method"), dict):
        description = ds3_value["historical_method"].get("description")
        if isinstance(description, str) and description:
            return description
    report_dir = ds1.get("report_dir")
    return Path(report_dir).name if isinstance(report_dir, str) else f"iteration-{iteration:02d}"


def comparability(
    method: dict[str, Any],
    ds1: dict[str, Any],
    ds3: dict[str, Any],
    ds3_value: dict[str, Any] | None,
) -> str:
    if ds3["status"] in NONTERMINAL or not ds3["is_terminal"]:
        return "pending DS3 terminal result"
    if ds3["status"] in {
        "missing_historical_artifact",
        "not_portable_legacy",
        "no_position_diagnostic",
        "superseded_no_replay",
    }:
        return "accounting/diagnostic only"
    if ds3["status"] == "terminal_control":
        return "sealed DS3 control; qualification metadata unavailable"
    if ds3["status"] in {
        "unqualified_boundary",
        "unqualified_numerical",
        "unqualified_parent",
        "unqualified_convergence",
        "unqualified_preflight",
    }:
        return "terminal but unqualified; estimate is diagnostic only"
    if (
        ds3_value
        and ds3_value.get("historical_method", {}).get(
            "scientifically_equivalent_to_numbered_iteration"
        )
        is False
    ):
        return "related control; not an exact replay"
    if ds1["status"] != "historical_terminal":
        return "DS1 historical artifact unavailable or diagnostic"
    if method.get("classification") == "superseded":
        return "historical method superseded; diagnostic comparison only"
    return "method-matched DS1/DS3 comparison"


def haversine_km(left: dict[str, float], right: dict[str, float]) -> float:
    """Great-circle distance used only after inference has been sealed."""
    latitude_1, longitude_1 = map(math.radians, (left["latitude_deg"], left["longitude_deg"]))
    latitude_2, longitude_2 = map(math.radians, (right["latitude_deg"], right["longitude_deg"]))
    a = (
        math.sin((latitude_2 - latitude_1) / 2) ** 2
        + math.cos(latitude_1)
        * math.cos(latitude_2)
        * math.sin((longitude_2 - longitude_1) / 2) ** 2
    )
    return 6371.0088 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def postseal_results(
    path: Path | None, matrix_sha256: str, registry_sha256: str
) -> tuple[dict[str, dict[str, Any]], dict[str, Any] | None]:
    """Read only a sealed post-seal evaluation bound to this matrix and registry."""
    if path is None:
        return {}, None
    value = verify(path)
    if value.get("schema") != "ds1-ds3-all-methods-postseal/v2":
        raise ValueError("invalid post-seal evaluation schema")
    if value.get("matrix_sha256") != matrix_sha256:
        raise ValueError("post-seal evaluation was produced from a different paired matrix")
    if value.get("method_registry_sha256") != registry_sha256:
        raise ValueError("post-seal evaluation was produced from a different method registry")
    rows = value.get("rows")
    if not isinstance(rows, list):
        raise ValueError("post-seal evaluation has no rows")
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("method_id"), str):
            raise ValueError("invalid post-seal evaluation row")
        if row["method_id"] in indexed:
            raise ValueError("duplicate method_id in post-seal evaluation")
        indexed[row["method_id"]] = row
    return indexed, {
        "path": portable_path(path),
        "sha256": digest(path),
        "source_comparison_sha256": value.get("comparison_sha256"),
    }


def build(
    matrix_path: Path,
    registry_path: Path = DEFAULT_REGISTRY,
    postseal_path: Path | None = None,
) -> dict[str, Any]:
    matrix = verify(matrix_path)
    if matrix.get("complete") not in (True, False) or not isinstance(matrix.get("rows"), list):
        raise ValueError("invalid paired completion matrix")
    matrix_sha256 = digest(matrix_path)
    registry, registry_sha256 = load_method_registry(registry_path, matrix_sha256)
    evaluated, evaluation_provenance = postseal_results(
        postseal_path, matrix_sha256, registry_sha256
    )
    iteration_rows = {int(row["iteration"]): row for row in matrix["rows"]}
    if set(iteration_rows) != set(range(1, 32)):
        raise ValueError("paired matrix must preserve the complete 1--31 iteration ledger")
    rows = []
    for method in registry["methods"]:
        method_id = method["method_id"]
        iteration = method.get("iteration")
        paired = iteration_rows.get(iteration) if isinstance(iteration, int) else None
        ds1 = {
            "status": method["ds1"]["terminal_status"],
            "report_dir": method["ds1"].get("report_dir"),
        }
        ds3, value, ds3_path, ds3_sha256, artifact_error = resolve_ds3_method(
            method, iteration_rows
        )
        ds1_postseal = postseal_from_report(ds1.get("report_dir"))
        ds1_qualification_info = ds1_qualification(ds1.get("report_dir"), iteration)
        ds3_estimates = arm_estimates(value, method["ds3_binding"])
        status = "unsealed_artifact" if artifact_error else ds3.get("status")
        evaluation = evaluated.get(method_id, {})
        per_estimate = {
            str(item.get("label")): item
            for item in evaluation.get("estimates", [])
            if isinstance(item, dict) and isinstance(item.get("label"), str)
        }
        for estimate in ds3_estimates:
            evaluated_estimate = per_estimate.get(estimate["label"])
            if evaluated_estimate:
                estimate["postseal_error_km"] = evaluated_estimate.get("postseal_error_km")
                estimate["ranking_eligible"] = evaluated_estimate.get("ranking_eligible")
        qualified_error = evaluation.get("best_qualified_error_km")
        diagnostic_error = evaluation.get("best_diagnostic_error_km")
        if qualified_error is not None and not isinstance(qualified_error, (float, int)):
            raise ValueError("invalid qualified post-seal error")
        if diagnostic_error is not None and not isinstance(diagnostic_error, (float, int)):
            raise ValueError("invalid diagnostic post-seal error")
        ds1_error = ds1_postseal["postseal_error_km"]
        rows.append(
            {
                "method_id": method_id,
                "iteration": iteration,
                "arm": method["arm"],
                "method": method["name"],
                "classification": method["classification"],
                "superseded_by": method.get("superseded_by"),
                "registry_aliases": method.get("registry_aliases", []),
                "ds1_scope": ds1.get("report_dir"),
                "ds3_scope": "DS3/all56",
                "ds1_terminal_status": ds1.get("status"),
                "ds1_qualification_status": ds1_qualification_info["status"],
                "ds1_ranking_eligible": ds1_qualification_info["ranking_eligible"],
                "ds1_qualification_reason": ds1_qualification_info["reason"],
                "ds3_terminal_status": status,
                "ds1_estimate": ds1_postseal["estimate"],
                "ds3_estimate": ds3_estimates[0] if len(ds3_estimates) == 1 else None,
                "ds3_estimates": ds3_estimates,
                "ds1_postseal_error_km": ds1_error,
                "ds3_qualified_postseal_error_km": qualified_error,
                "ds3_diagnostic_postseal_error_km": diagnostic_error,
                "postseal_delta_km": (
                    float(qualified_error) - ds1_error
                    if (
                        qualified_error is not None
                        and ds1_error is not None
                        and ds1_qualification_info["ranking_eligible"]
                    )
                    else None
                ),
                "ds3_objective": objective(value),
                "ds3_runtime_s": runtime(value),
                "ds3_support": support(value),
                "qualification_reason": (value or {}).get(
                    "reason", artifact_error or ds3.get("status")
                ),
                "comparability": (
                    "unsealed or missing DS3 artifact"
                    if artifact_error
                    else comparability(method, ds1, ds3, value)
                ),
                "ds1_postseal_artifact": ds1_postseal["artifact"],
                "ds1_postseal_artifact_sha256": ds1_postseal["artifact_sha256"],
                "ds1_qualification_artifact": ds1_qualification_info["artifact"],
                "ds1_qualification_artifact_sha256": ds1_qualification_info["artifact_sha256"],
                "ds3_artifact": ds3_path,
                "ds3_artifact_sha256": ds3_sha256,
                "method_terminal": bool(ds3.get("is_terminal")) and not artifact_error,
                "iteration_ledger_terminal": (
                    bool(paired.get("paired_terminal")) if paired else None
                ),
            }
        )
    pending_method_ids = [
        row["method_id"]
        for row in rows
        if row["ds3_terminal_status"] in NONTERMINAL or not row["method_terminal"]
    ]
    pending_iterations = sorted(
        {
            row["iteration"]
            for row in rows
            if row["method_id"] in pending_method_ids and row["iteration"]
        }
    )
    return {
        "schema": "ds1-ds3-all-methods-report/v2",
        "complete": not pending_method_ids,
        "publication_ready": not pending_method_ids,
        "matrix": {"path": portable_path(matrix_path), "sha256": matrix_sha256},
        "method_registry": {
            "path": portable_path(registry_path),
            "sha256": registry_sha256,
        },
        "postseal_evaluation": evaluation_provenance,
        "required_pending_method_ids": pending_method_ids,
        "required_pending_iterations": pending_iterations,
        "rows": rows,
        "counts": {
            "method_arms": len(rows),
            "pending_method_arms": len(pending_method_ids),
            "terminal_method_arms": len(rows) - len(pending_method_ids),
            "iteration_slots": len(iteration_rows),
        },
    }


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fields = [
        "method_id",
        "iteration",
        "arm",
        "method",
        "classification",
        "superseded_by",
        "registry_aliases",
        "ds1_scope",
        "ds3_scope",
        "ds1_terminal_status",
        "ds1_qualification_status",
        "ds1_ranking_eligible",
        "ds1_qualification_reason",
        "ds3_terminal_status",
        "ds1_estimate",
        "ds3_estimate",
        "ds1_postseal_error_km",
        "ds3_qualified_postseal_error_km",
        "ds3_diagnostic_postseal_error_km",
        "postseal_delta_km",
        "ds3_objective",
        "ds3_runtime_s",
        "ds3_support",
        "qualification_reason",
        "comparability",
        "ds1_postseal_artifact",
        "ds1_postseal_artifact_sha256",
        "ds1_qualification_artifact",
        "ds1_qualification_artifact_sha256",
        "ds3_artifact",
        "ds3_artifact_sha256",
        "method_terminal",
        "iteration_ledger_terminal",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(row[key], sort_keys=True)
                    if isinstance(row[key], (dict, list))
                    else row[key]
                    for key in fields
                }
            )


def estimate_rows(value: dict[str, Any], *, qualified_only: bool) -> list[dict[str, Any]]:
    """Flatten post-seal estimates while preserving their ranking eligibility."""
    result: list[dict[str, Any]] = []
    for row in value["rows"]:
        status = row["ds3_terminal_status"]
        ds3_eligible = status == "qualified"
        eligible = bool(row["ds1_ranking_eligible"]) and ds3_eligible
        if qualified_only and not eligible:
            continue
        for estimate in row["ds3_estimates"]:
            # The evaluation rows preserve errors per label.  The summary's best
            # value remains useful when labels are not present in older records.
            result.append(
                {
                    "method_id": row["method_id"],
                    "iteration": row["iteration"],
                    "arm": row["arm"],
                    "method": row["method"],
                    "terminal_status": status,
                    "ranking_eligible": eligible,
                    "ds1_ranking_eligible": row["ds1_ranking_eligible"],
                    "ds3_ranking_eligible": ds3_eligible,
                    "estimate_label": estimate["label"],
                    "latitude_deg": estimate["latitude_deg"],
                    "longitude_deg": estimate["longitude_deg"],
                    "postseal_error_km": estimate.get("postseal_error_km"),
                    "ds1_postseal_error_km": row["ds1_postseal_error_km"],
                    "ds3_artifact": row["ds3_artifact"],
                    "ds3_artifact_sha256": row["ds3_artifact_sha256"],
                }
            )
    return result


def write_estimate_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fields = [
        "method_id",
        "iteration",
        "arm",
        "method",
        "terminal_status",
        "ranking_eligible",
        "ds1_ranking_eligible",
        "ds3_ranking_eligible",
        "estimate_label",
        "latitude_deg",
        "longitude_deg",
        "postseal_error_km",
        "ds1_postseal_error_km",
        "ds3_artifact",
        "ds3_artifact_sha256",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def plot_error_scatter(
    rows: list[dict[str, Any]], output: Path, title: str, *, require_eligible: bool
) -> None:
    figure, axis = plt.subplots(figsize=(6, 4.5), constrained_layout=True)
    usable = [
        row
        for row in rows
        if (row["ranking_eligible"] or not require_eligible)
        and row["ds1_postseal_error_km"] is not None
        and row["postseal_error_km"] is not None
    ]
    if usable:
        colors = ["#457b9d" if row["ranking_eligible"] else "#e76f51" for row in usable]
        axis.scatter(
            [row["ds1_postseal_error_km"] for row in usable],
            [row["postseal_error_km"] for row in usable],
            c=colors,
        )
        maximum = max(
            max(row["ds1_postseal_error_km"] for row in usable),
            max(row["postseal_error_km"] for row in usable),
        )
        axis.plot([0, maximum], [0, maximum], color="#6c757d", linewidth=1)
        axis.set_xlabel("DS1 post-seal error (km)")
        axis.set_ylabel("DS3 post-seal error (km)")
    else:
        axis.text(0.5, 0.5, "No paired post-seal errors are available", ha="center", va="center")
        axis.set_axis_off()
    axis.set_title(title)
    figure.savefig(output, dpi=180)
    plt.close(figure)


def plots(value: dict[str, Any], output: Path) -> None:
    rows = value["rows"]
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    pending_ids = set(value["required_pending_method_ids"])
    pending = [row["method_id"] for row in rows if row["method_id"] in pending_ids]
    done = [row["method_id"] for row in rows if row["method_id"] not in pending_ids]
    axes[0].bar(["terminal", "pending"], [len(done), len(pending)], color=["#2a9d8f", "#e76f51"])
    axes[0].set_title("Method-arm completion")
    axes[0].set_ylabel("Method arms")
    valid = [
        row
        for row in rows
        if row["ds1_postseal_error_km"] is not None
        and row["ds1_ranking_eligible"]
        and row["ds3_qualified_postseal_error_km"] is not None
    ]
    if valid:
        axes[1].scatter(
            [row["ds1_postseal_error_km"] for row in valid],
            [row["ds3_qualified_postseal_error_km"] for row in valid],
            color="#457b9d",
        )
        maximum = max(max(axes[1].get_xlim()), max(axes[1].get_ylim()))
        axes[1].plot([0, maximum], [0, maximum], color="#6c757d")
        axes[1].set_xlabel("DS1 post-seal error (km)")
        axes[1].set_ylabel("DS3 post-seal error (km)")
    else:
        axes[1].text(
            0.5,
            0.5,
            "No paired post-seal errors are available",
            ha="center",
            va="center",
            transform=axes[1].transAxes,
        )
        axes[1].set_axis_off()
    axes[1].set_title("Comparable post-seal errors")
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=180)
    plt.close(figure)


def markdown(value: dict[str, Any]) -> str:
    lines = [
        "# DS1 vs DS3 all-method report",
        "",
        f"Publication ready: **{value['publication_ready']}**.",
        "",
        "DS1 `unavailable` qualification means no sealed DS1 qualification record, "
        "not necessarily that no historical method result exists. "
        "`DS1_COVERAGE_AUDIT.md` lists sealed, exact-method multi-case evidence "
        "separately; it is not promoted into a ranking aggregate.",
        "",
    ]
    if value["required_pending_method_ids"]:
        pending = ", ".join(value["required_pending_method_ids"])
        lines.extend(
            [
                f"Required DS3 method arms are pending for: {pending}.",
                "",
            ]
        )
    lines.extend(
        [
            "| Method ID | Iteration | Class | DS1 qualification | DS3 | "
            "DS1 error km | DS3 qualified km | "
            "DS3 diagnostic km | Delta km | Comparability |",
            "| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in value["rows"]:

        def number(item: float | None) -> str:
            return "—" if item is None else f"{item:.3f}"

        lines.append(
            (
                "| {method_id} | {iteration} | {classification} | "
                "{ds1_qualification} | {ds3} | {ds1_error} | "
                "{ds3_qualified_error} | "
                "{ds3_diagnostic_error} | {delta} | {comparison} |"
            ).format(
                method_id=row["method_id"],
                iteration=row["iteration"],
                classification=row["classification"],
                ds1_qualification=row["ds1_qualification_status"],
                ds3=row["ds3_terminal_status"],
                ds1_error=number(row["ds1_postseal_error_km"]),
                ds3_qualified_error=number(row["ds3_qualified_postseal_error_km"]),
                ds3_diagnostic_error=number(row["ds3_diagnostic_postseal_error_km"]),
                delta=number(row["postseal_delta_km"]),
                comparison=row["comparability"],
            )
        )
    diagnostic = [
        row for row in value["rows"] if row["ds3_diagnostic_postseal_error_km"] is not None
    ]
    lines.extend(
        [
            "",
            "## Diagnostic unqualified estimates",
            "",
            "These errors are post-seal diagnostics only. They are excluded from "
            "qualified-method ranking.",
            "",
            "| Method ID | Iteration | Terminal status | Diagnostic error km |",
            "| --- | ---: | --- | ---: |",
        ]
    )
    lines.extend(
        "| {method_id} | {iteration} | {status} | {error:.3f} |".format(
            method_id=row["method_id"],
            iteration=row["iteration"],
            status=row["ds3_terminal_status"],
            error=row["ds3_diagnostic_postseal_error_km"],
        )
        for row in diagnostic
    )
    ds1_diagnostic = [
        row
        for row in value["rows"]
        if row["ds1_postseal_error_km"] is not None and not row["ds1_ranking_eligible"]
    ]
    lines.extend(
        [
            "",
            "## DS1 diagnostic estimates",
            "",
            "These historical errors are retained for audit but are excluded from rankings.",
            "",
            "| Method ID | Iteration | DS1 qualification | Diagnostic error km | Reason |",
            "| --- | ---: | --- | ---: | --- |",
        ]
    )
    lines.extend(
        "| {method_id} | {iteration} | {status} | {error:.3f} | {reason} |".format(
            method_id=row["method_id"],
            iteration=row["iteration"],
            status=row["ds1_qualification_status"],
            error=row["ds1_postseal_error_km"],
            reason=row["ds1_qualification_reason"],
        )
        for row in ds1_diagnostic
    )
    return "\n".join(lines) + "\n"


def evaluate_postseal(
    comparison_path: Path, output: Path, reference: dict[str, float]
) -> dict[str, Any]:
    """Measure sealed estimates against a supplied reference after inference.

    The reference is deliberately consumed only here.  A terminal unqualified
    estimate receives an error for debugging but its `ranking_eligible` flag is
    false and it cannot enter the qualified comparison table or plot.
    """
    comparison = verify(comparison_path)
    if comparison.get("schema") != "ds1-ds3-all-methods-report/v2":
        raise ValueError("invalid comparison schema")
    matrix = comparison.get("matrix")
    if not isinstance(matrix, dict) or not isinstance(matrix.get("sha256"), str):
        raise ValueError("comparison has no sealed matrix provenance")
    registry = comparison.get("method_registry")
    if not isinstance(registry, dict) or not isinstance(registry.get("sha256"), str):
        raise ValueError("comparison has no sealed method-registry provenance")
    rows: list[dict[str, Any]] = []
    for source in comparison.get("rows", []):
        if not isinstance(source, dict):
            raise ValueError("invalid comparison row")
        status = source.get("ds3_terminal_status")
        terminal = status in TERMINAL
        eligible = status == "qualified"
        measured = []
        for estimate in source.get("ds3_estimates", []):
            if not terminal or not isinstance(estimate, dict):
                continue
            candidate = point({"estimated_position": estimate})
            if candidate is None:
                continue
            measured.append(
                {
                    "label": str(estimate.get("label", "selected")),
                    **candidate,
                    "postseal_error_km": haversine_km(candidate, reference),
                    "ranking_eligible": eligible,
                    "classification": "qualified" if eligible else "diagnostic_unqualified",
                }
            )
        errors = [item["postseal_error_km"] for item in measured]
        rows.append(
            {
                "method_id": source["method_id"],
                "iteration": source["iteration"],
                "ds3_terminal_status": status,
                "estimates": measured,
                "best_qualified_error_km": min(errors) if eligible and errors else None,
                "best_diagnostic_error_km": min(errors) if not eligible and errors else None,
            }
        )
    value = {
        "schema": "ds1-ds3-all-methods-postseal/v2",
        "comparison_sha256": digest(comparison_path),
        "matrix_sha256": matrix["sha256"],
        "method_registry_sha256": registry["sha256"],
        "reference_coordinate": {
            **reference,
            "use": "post-seal diagnostic and reporting only; never supplied to inference",
        },
        "rows": rows,
    }
    write(output, value)
    return value


def generate(
    matrix: Path,
    registry: Path,
    output_dir: Path,
    postseal_path: Path | None = None,
) -> dict[str, Any]:
    value = build(matrix, registry, postseal_path)
    write(output_dir / "comparison.json", value)
    write_csv(value["rows"], output_dir / "comparison.csv")
    qualified = estimate_rows(value, qualified_only=True)
    all_estimates = estimate_rows(value, qualified_only=False)
    write_estimate_csv(qualified, output_dir / "qualified-only.csv")
    write_estimate_csv(all_estimates, output_dir / "all-estimates.csv")
    (output_dir / "REPORT.md").write_text(markdown(value))
    plots(value, output_dir / "comparison.png")
    plot_error_scatter(
        qualified,
        output_dir / "qualified-only.png",
        "Qualified-only post-seal errors",
        require_eligible=True,
    )
    plot_error_scatter(
        all_estimates,
        output_dir / "all-estimates.png",
        "All estimates: qualified plus unqualified diagnostics",
        require_eligible=False,
    )
    return value


def publish(comparison: Path) -> None:
    value = verify(comparison)
    if value.get("publication_ready") is not True:
        raise ValueError("refusing publication: required DS3 rows remain pending")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    generate_parser = sub.add_parser("generate")
    generate_parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    generate_parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    generate_parser.add_argument("--output-dir", type=Path, default=HERE)
    generate_parser.add_argument(
        "--postseal",
        type=Path,
        help="sealed post-seal evaluation bound to the same paired matrix",
    )
    evaluate_parser = sub.add_parser("postseal")
    evaluate_parser.add_argument("--comparison", type=Path, default=HERE / "comparison.json")
    evaluate_parser.add_argument("--output", type=Path, default=HERE / "postseal-evaluation.json")
    evaluate_parser.add_argument("--reference-latitude", type=float, required=True)
    evaluate_parser.add_argument("--reference-longitude", type=float, required=True)
    publish_parser = sub.add_parser("publish")
    publish_parser.add_argument("--comparison", type=Path, default=HERE / "comparison.json")
    args = parser.parse_args()
    if args.command == "generate":
        print(
            json.dumps(
                generate(args.matrix, args.registry, args.output_dir, args.postseal)["counts"],
                sort_keys=True,
            )
        )
    elif args.command == "postseal":
        reference = {
            "latitude_deg": args.reference_latitude,
            "longitude_deg": args.reference_longitude,
        }
        evaluation = evaluate_postseal(args.comparison, args.output, reference)
        print(json.dumps(evaluation, sort_keys=True))
    else:
        publish(args.comparison)


if __name__ == "__main__":
    main()
