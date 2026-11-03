import hashlib
import json

import numpy as np
from bundle import Data
from evaluate import coordinates, ecef
from selection import MANIFEST, MODEL_NAMES, ROOT, select

SCIENTIFIC_SOURCES = (
    ROOT / "models.py",
    ROOT / "bundle.py",
    ROOT / "fast_geometry.py",
    ROOT / "fast_tracks.py",
    *(
        ROOT.parent / "2026_10_02_coherent_localization" / filename
        for filename in ("common.py", "anchors.py", "association.py", "refinement.py")
    ),
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def model_matrix_issues(fits, rows, expected_models=MODEL_NAMES):
    """Return completeness issues without requiring optimizer success."""
    issues = []
    models = fits.get("models")
    if not isinstance(models, dict):
        return ["model matrix missing or invalid"]

    expected = set(expected_models)
    actual = set(models)
    if actual != expected:
        issues.append("model matrix incomplete")

    for model in expected_models:
        fitted = models.get(model)
        row = rows.get(model)
        if fitted is None:
            issues.append(f"{model}: missing fit receipt")
        elif not isinstance(fitted, dict):
            issues.append(f"{model}: invalid fit receipt")
        else:
            attempted = bool(fitted.get("attempted", True))
            if not attempted:
                issues.append(f"{model}: never attempted")
            if fitted.get("status") == "error":
                issues.append(f"{model}: implementation/runtime error")
            if fitted.get("model", model) != model:
                issues.append(f"{model}: fit receipt model identity mismatch")

        if row is None:
            issues.append(f"{model}: missing comparison row")
            continue
        if not isinstance(row, dict):
            issues.append(f"{model}: invalid comparison row")
            continue
        if fitted is None or not isinstance(fitted, dict):
            continue

        attempted = bool(fitted.get("attempted", True))
        success = bool(fitted.get("success", False))
        if bool(row.get("attempted", False)) != attempted:
            issues.append(f"{model}: attempted status not preserved")
        if bool(row.get("success", False)) != success:
            issues.append(f"{model}: success status not preserved")
        if row.get("status") != fitted.get("status", "finished"):
            issues.append(f"{model}: fit status not preserved")
        for field in ("initialization_provenance", "rx_policy"):
            if row.get(field) != fitted.get(field):
                issues.append(f"{model}: {field} not preserved")
    return issues


def provenance_issues(
    fits,
    current_inputs,
    current_sources,
    fit_digest,
    table_fit_digest,
):
    """Compare a fit receipt with current inputs, sources, and evaluation binding."""
    issues = []
    recorded_inputs = fits.get("input_sha256", {})
    for name, current in current_inputs.items():
        if recorded_inputs.get(name) != current:
            issues.append(f"fit input has changed: {name}")

    recorded_sources = fits.get("source_sha256", {})
    for name, current in current_sources.items():
        if recorded_sources.get(name) != current:
            issues.append(f"scientific implementation changed: {name}")

    if table_fit_digest != fit_digest:
        issues.append("comparison table does not bind current fit receipts")
    return issues


def _comparison_index(rows):
    indexed = {}
    duplicates = False
    invalid = False
    for row in rows:
        if not isinstance(row, dict) or "session_id" not in row or "model" not in row:
            invalid = True
            continue
        key = (row["session_id"], row["model"])
        if key in indexed:
            duplicates = True
        indexed[key] = row
    return indexed, duplicates, invalid


def main():
    selection = json.loads((ROOT / "selection.json").read_text())
    population = json.loads(MANIFEST.read_text())
    sessions = [selection["original_sample"], *selection["selected"]]
    checks = {
        "frozen_population_digest": digest(MANIFEST) == selection["manifest_sha256"],
        "reproducible_random_selection": select(population["captures"]) == selection["selected"],
        "sixteen_distinct_single_scans": len(selection["selected"])
        == len(set(selection["selected"]))
        == 16,
        "seventeen_distinct_benchmark_cases": len(sessions) == len(set(sessions)) == 17,
        "exact_model_scope": selection["models"] == list(MODEL_NAMES),
    }
    table_path = ROOT / "comparison.json"
    table = (
        json.loads(table_path.read_text())
        if table_path.exists()
        else {"rows": [], "fits_sha256": {}}
    )
    table_rows = table.get("rows", [])
    if not isinstance(table_rows, list):
        table_rows = []
    indexed, duplicate_rows, invalid_rows = _comparison_index(table_rows)
    expected_cells = {(session, model) for session in sessions for model in MODEL_NAMES}
    checks["221_comparison_cells"] = (
        not duplicate_rows
        and not invalid_rows
        and len(table_rows) == len(expected_cells)
        and set(indexed) == expected_cells
    )

    current_sources = {
        str(source.relative_to(ROOT.parent)): digest(source) for source in SCIENTIFIC_SOURCES
    }
    table_fit_digests = table.get("fits_sha256", {})
    if not isinstance(table_fit_digests, dict):
        table_fit_digests = {}

    cases = []
    for session in sessions:
        directory = ROOT / "scans" / session
        case = {"session_id": session, "issues": []}
        try:
            data = Data(directory)
            fits_path = directory / "fits.json"
            fits = json.loads(fits_path.read_text())
            truth = json.loads((directory / "evaluation.json").read_text())
            if (
                truth.get("session_id") != session
                or data.session_id != session
                or fits.get("session_id") != session
            ):
                case["issues"].append("session identity mismatch")
            expected_dataset = (
                "original_sample" if session == selection["original_sample"] else "DS11"
            )
            if fits.get("dataset") != expected_dataset:
                case["issues"].append("fit dataset identity mismatch")
            if fits.get("expected_models") != list(MODEL_NAMES):
                case["issues"].append("fit expected model scope mismatch")
            if fits.get("status") != "finished":
                case["issues"].append("fit driver has not finished")

            current_inputs = {
                name: digest(directory / name) for name in ("bundle.json", "bundle.npz")
            }
            if truth.get("bundle_npz_sha256") != current_inputs["bundle.npz"]:
                case["issues"].append("evaluation reference is not bound to bundle")
            case["issues"].extend(
                provenance_issues(
                    fits,
                    current_inputs,
                    current_sources,
                    digest(fits_path),
                    table_fit_digests.get(session),
                )
            )

            rows = {model: indexed.get((session, model)) for model in MODEL_NAMES}
            case["issues"].extend(model_matrix_issues(fits, rows))
            for model, fitted in fits.get("models", {}).items():
                row = rows.get(model)
                if (
                    model not in MODEL_NAMES
                    or not isinstance(fitted, dict)
                    or row is None
                    or not bool(fitted.get("success", False))
                ):
                    continue
                parameters = np.asarray(fitted.get("parameters", []), dtype=float)
                if parameters.size < 2 or not np.all(np.isfinite(parameters[:2])):
                    case["issues"].append(f"{model}: successful fit lacks finite position")
                    continue
                reference = truth["reference_site"]
                error = float(
                    np.linalg.norm(
                        ecef(*coordinates(parameters[:2]))
                        - ecef(reference["latitude_deg"], reference["longitude_deg"])
                    )
                )
                if row.get("reference_error_km") is None or not np.isclose(
                    row["reference_error_km"], error
                ):
                    case["issues"].append(f"{model}: reported reference error mismatch")
            case["observations"] = len(data.times)
            case["source_groups"] = len(np.unique(data.group))
            case["successful_models"] = sum(
                bool(fit.get("success", False))
                for fit in fits.get("models", {}).values()
                if isinstance(fit, dict)
            )
        except (OSError, KeyError, TypeError, ValueError) as error:
            case["issues"].append(f"{type(error).__name__}: {error}")
        cases.append(case)

    complete = all(checks.values()) and all(not case["issues"] for case in cases)
    report = {
        "complete": complete,
        "checks": checks,
        "cases": cases,
        "scope": (
            "All models attempted, errors distinguished from rejection/nonconvergence; "
            "no superiority claim"
        ),
    }
    (ROOT / "completion-audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "complete": complete,
                "cases_without_issues": sum(not case["issues"] for case in cases),
                "total_cases": len(cases),
            }
        )
    )


if __name__ == "__main__":
    main()
