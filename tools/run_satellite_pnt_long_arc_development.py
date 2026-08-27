#!/usr/bin/env python3
"""Execute the one hash-authorized opened-long-arc development run.

The tool is deliberately unusable without an additive execution amendment. It
verifies the base protocol, implementation commit and file hashes, exact raw
TLE bytes, and exclusive output paths before constructing any catalogue field
or consuming response scores. Outputs remain opened-development evidence and
cannot support a secure NORAD or positioning claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.catalogue_population import StarlinkHorizonPopulationPolicy
from leo.analysis.catalogue_prediction import (
    ExactTauPolicy,
    Sgp4SupportPredictionPolicy,
    TauGridPoint,
)
from leo.analysis.research.long_arc_catalogue_adapter import (
    load_registered_long_arc_graph,
)
from leo.analysis.research.long_arc_satellite_pnt_runner import (
    LongArcDevelopmentRunResult,
    LongArcExecutionDesign,
    long_arc_development_result_payload,
    run_long_arc_development_analysis,
)
from leo.analysis.research.satellite_pnt_long_arc_protocol import (
    load_satellite_pnt_long_arc_protocol,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1

DEFAULT_AMENDMENT = Path(
    "config/analysis/satellite-pnt-long-arc-development-execution-amendment-v1.json"
)
_SCHEMA = "org.leo.research.satellite-pnt-long-arc-execution-amendment/v1"
_IMPLEMENTATION_FILES = (
    "src/leo/analysis/catalogue_population.py",
    "src/leo/analysis/catalogue_prediction.py",
    "src/leo/analysis/nearest_neighbour_association.py",
    "src/leo/analysis/research/long_arc_catalogue_adapter.py",
    "src/leo/analysis/research/long_arc_satellite_pnt_runner.py",
    "src/leo/analysis/research/radio_polynomial_null.py",
    "src/leo/analysis/research/satellite_pnt_long_arc_protocol.py",
    "src/leo/contracts/catalogue_association.py",
    "tools/run_satellite_pnt_long_arc_development.py",
)


class LongArcExecutionAuthorityError(ValueError):
    """The additive amendment or its frozen execution environment drifted."""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--execution-amendment", type=Path, default=DEFAULT_AMENDMENT)
    return parser.parse_args()


def validate_execution_amendment(
    repository_root: Path,
    amendment_path: Path,
) -> dict[str, Any]:
    """Validate all execution authority before output creation or scientific work."""

    root = repository_root.resolve()
    path = _resolve_input(root, amendment_path)
    amendment = _load_json_object(path)
    expected_keys = {
        "schema",
        "amendment_id",
        "status",
        "chronology",
        "base_protocol",
        "implementation",
        "raw_tle_inputs",
        "numerical_controls",
        "outputs",
        "execution",
        "claim_boundary",
        "amendment_digest",
    }
    if set(amendment) != expected_keys or amendment.get("schema") != _SCHEMA:
        raise LongArcExecutionAuthorityError("execution amendment schema is not exact")
    digest = canonical_digest(
        {key: value for key, value in amendment.items() if key != "amendment_digest"}
    )
    if amendment.get("amendment_digest") != digest:
        raise LongArcExecutionAuthorityError("execution amendment semantic digest drifted")
    if amendment.get(
        "status"
    ) != "frozen-authority-for-one-opened-development-execution" or amendment.get("execution") != {
        "authorized": True,
        "maximum_attempt_count": 1,
        "attempt_number": 1,
        "outputs_must_not_exist_before_execution": True,
        "response_scoring_before_this_amendment": False,
        "new_rf_collection_authorized": False,
    }:
        raise LongArcExecutionAuthorityError("execution authority or attempt count differs")
    _validate_claim_boundary(amendment["claim_boundary"])
    _validate_base_protocol(root, amendment["base_protocol"])
    _validate_implementation(root, amendment["implementation"])
    _validate_raw_tle_inputs(amendment["raw_tle_inputs"])
    _validate_numerical_controls(amendment["numerical_controls"])
    _validate_output_paths(root, amendment["outputs"])
    return amendment


def execute_authorized_development_run(
    repository_root: Path,
    amendment_path: Path,
) -> tuple[Path, Path]:
    """Run both exact opened arcs once and publish digest-bound outputs."""

    root = repository_root.resolve()
    amendment = validate_execution_amendment(root, amendment_path)
    output = amendment["outputs"]
    receipt_path = _resolve_new_output(root, output["attempt_receipt_path"])
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    started_utc = datetime.now(UTC).isoformat()
    receipt_base = {
        "schema": "org.leo.research.satellite-pnt-long-arc-execution-receipt/v1",
        "amendment_id": amendment["amendment_id"],
        "amendment_digest": amendment["amendment_digest"],
        "implementation_commit": amendment["implementation"]["commit"],
        "repository_head_at_start": _git(root, "rev-parse", "HEAD"),
        "repository_tree_at_start": _git(root, "rev-parse", "HEAD^{tree}"),
        "started_utc": started_utc,
        "attempt_number": 1,
    }
    _write_json_exclusive(receipt_path, {**receipt_base, "status": "running"})
    try:
        artifact_dir, report_path = _execute_after_attempt_seal(
            root=root,
            amendment_path=amendment_path,
            amendment=amendment,
        )
    except BaseException as error:
        _write_json(
            receipt_path,
            {
                **receipt_base,
                "status": "failed",
                "finished_utc": datetime.now(UTC).isoformat(),
                "exception_type": type(error).__name__,
                "exception_message": str(error),
            },
        )
        raise
    _write_json(
        receipt_path,
        {
            **receipt_base,
            "status": "complete",
            "finished_utc": datetime.now(UTC).isoformat(),
            "artifact_directory": artifact_dir.relative_to(root).as_posix(),
            "manifest_sha256": _sha256_file(artifact_dir / "manifest.json"),
            "report_path": report_path.relative_to(root).as_posix(),
            "report_sha256": _sha256_file(report_path),
        },
    )
    return artifact_dir, report_path


def _execute_after_attempt_seal(
    *,
    root: Path,
    amendment_path: Path,
    amendment: dict[str, Any],
) -> tuple[Path, Path]:
    protocol_binding = amendment["base_protocol"]
    protocol_path = _resolve_input(root, Path(protocol_binding["path"]))
    protocol = load_satellite_pnt_long_arc_protocol(protocol_path, repository_root=root)
    if protocol.protocol_digest != protocol_binding["protocol_digest"]:
        raise LongArcExecutionAuthorityError("base protocol semantic digest differs")
    controls = amendment["numerical_controls"]
    tau = ExactTauPolicy(
        policy="bounded-profile-minus5-plus5-v1",
        points=tuple(
            TauGridPoint(
                controls["tau_lower_s"] + index * controls["tau_step_s"],
                0.0,
            )
            for index in range(controls["tau_state_count"])
        ),
    )
    design = LongArcExecutionDesign(
        selection_protocol_digest=protocol.protocol_digest,
        nominal_rf_hz=protocol.models.nominal_rf_hz,
        nuisance_offset_prior_sigma_hz=protocol.models.component_offset_prior_sigma_hz,
        calendar_block_duration_s=protocol.split_and_scoring.calendar_block_duration_s,
        tau_policy=tau,
        population_policy=StarlinkHorizonPopulationPolicy(
            coarse_spacing_s=controls["population_coarse_spacing_s"],
            maximum_coarse_time_count=controls["population_maximum_coarse_time_count"],
            maximum_exact_time_count=controls["population_maximum_exact_time_count"],
            maximum_coarse_propagated_states=(
                controls["population_maximum_coarse_propagated_states"]
            ),
            maximum_exact_propagated_states=(
                controls["population_maximum_exact_propagated_states"]
            ),
            maximum_selected_candidate_count=controls["maximum_candidate_count"],
        ),
        prediction_policy=Sgp4SupportPredictionPolicy(
            integration_sample_count=controls["support_integration_sample_count"],
            standard_uncertainty_floor_hz=controls["prediction_uncertainty_floor_hz"],
            element_age_growth_hz_per_day=(controls["prediction_element_age_growth_hz_per_day"]),
            fit_residual_multiplier=controls["prediction_fit_residual_multiplier"],
            maximum_propagated_states=controls["prediction_maximum_propagated_states"],
        ),
    )
    site = ObserverSiteV1(
        latitude_deg=protocol.observer.latitude_deg,
        longitude_deg=protocol.observer.longitude_deg,
        altitude_m=protocol.observer.altitude_m,
        label=protocol.observer.name,
    )
    tle_by_arc = {item["arc_id"]: item for item in amendment["raw_tle_inputs"]}
    results: list[LongArcDevelopmentRunResult] = []
    for observation in protocol.observations:
        binding = tle_by_arc[observation.arc_id]
        payload_path = Path(binding["path"])
        payload = payload_path.read_bytes()
        if _sha256_bytes(payload) != binding["sha256"]:
            raise LongArcExecutionAuthorityError("raw TLE bytes changed after preflight")
        bundle = load_registered_long_arc_graph(
            protocol_path,
            repository_root=root,
            arc_id=observation.arc_id,
        )
        results.append(
            run_long_arc_development_analysis(
                arc_id=observation.arc_id,
                graph=bundle.graph,
                prediction_support=bundle.prediction_support,
                snapshot_payload=payload,
                tle_snapshot=TleSnapshotRefV1(
                    provider=observation.tle_snapshot.provider,
                    collected_utc_ns=observation.tle_snapshot.collected_utc_ns,
                    digest=observation.tle_snapshot.raw_sha256,
                    object_count=observation.tle_snapshot.object_count,
                ),
                observer_site=site,
                design=design,
            )
        )

    output = amendment["outputs"]
    artifact_dir = _resolve_new_output(root, output["artifact_directory"])
    report_path = _resolve_new_output(root, output["report_path"])
    _publish_outputs(
        root=root,
        amendment_path=_resolve_input(root, amendment_path),
        amendment=amendment,
        results=tuple(results),
        artifact_dir=artifact_dir,
        report_path=report_path,
    )
    return artifact_dir, report_path


def _publish_outputs(
    *,
    root: Path,
    amendment_path: Path,
    amendment: dict[str, Any],
    results: tuple[LongArcDevelopmentRunResult, ...],
    artifact_dir: Path,
    report_path: Path,
) -> None:
    if artifact_dir.exists() or report_path.exists():
        raise LongArcExecutionAuthorityError("exclusive output path appeared during execution")
    artifact_dir.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    stage_root = Path(tempfile.mkdtemp(prefix=".satellite-pnt-long-arc-", dir=artifact_dir.parent))
    stage_artifacts = stage_root / artifact_dir.name
    stage_artifacts.mkdir()
    try:
        result_paths: list[Path] = []
        figure_paths: list[Path] = []
        for result in results:
            short = "9981" if "9981" in result.arc_id else "150802"
            result_path = stage_artifacts / f"{short}-result.json"
            _write_json(result_path, long_arc_development_result_payload(result))
            result_paths.append(result_path)
            figure_paths.extend(_render_figures(stage_artifacts, short, result))
        report_text = _render_report(amendment, results, artifact_dir, report_path)
        stage_report = stage_root / report_path.name
        stage_report.write_text(report_text, encoding="utf-8")
        manifest_payload = {
            "schema": "org.leo.research.satellite-pnt-long-arc-development-result-manifest/v1",
            "execution_amendment": {
                "path": amendment_path.relative_to(root).as_posix(),
                "sha256": _sha256_file(amendment_path),
                "semantic_digest": amendment["amendment_digest"],
            },
            "implementation_commit": amendment["implementation"]["commit"],
            "results": [
                {
                    "arc_id": result.arc_id,
                    "result_digest": result.result_digest,
                    "path": path.name,
                    "sha256": _sha256_file(path),
                }
                for result, path in zip(results, result_paths, strict=True)
            ],
            "figures": [{"path": path.name, "sha256": _sha256_file(path)} for path in figure_paths],
            "report": {
                "path": report_path.relative_to(root).as_posix(),
                "sha256": _sha256_file(stage_report),
            },
            "claim_boundary": amendment["claim_boundary"],
        }
        manifest = {
            **manifest_payload,
            "manifest_digest": canonical_digest(manifest_payload),
        }
        _write_json(stage_artifacts / "manifest.json", manifest)
        stage_artifacts.rename(artifact_dir)
        stage_report.replace(report_path)
    finally:
        if stage_root.exists():
            shutil.rmtree(stage_root)


def _render_figures(
    directory: Path,
    short: str,
    result: LongArcDevelopmentRunResult,
) -> tuple[Path, Path]:
    main = result.partitions[0]
    true_field = next(item for item in main.field_scores if item.field_delta_s == 0)
    catalogue_scores = tuple(
        item for item in true_field.association.scores if item.kind == "catalogue-candidate"
    )[:5]
    tau_path = directory / f"{short}-main-tau-profiles.png"
    figure, axis = plt.subplots(figsize=(9.0, 5.2), constrained_layout=True)
    for score in catalogue_scores:
        values = score.tau_profile_training_scores
        minimum = min(item.training_total_negative_log_score for item in values)
        axis.plot(
            [item.tau_s for item in values],
            [item.training_total_negative_log_score - minimum for item in values],
            marker=".",
            linewidth=1.2,
            label=f"NORAD {score.catalog_number}",
        )
    axis.set_title(f"{short}: main training tau profiles (descriptive)")
    axis.set_xlabel("Equivalent epoch sensitivity tau (s)")
    axis.set_ylabel("Delta training negative log score")
    axis.grid(alpha=0.25)
    axis.legend(fontsize=8)
    figure.savefig(tau_path, dpi=160)
    plt.close(figure)

    comparison_path = directory / f"{short}-future-model-comparison.png"
    figure, axis = plt.subplots(figsize=(10.0, 5.6), constrained_layout=True)
    labels = [item.label for item in result.partitions]
    orbit = [
        next(
            field for field in item.field_scores if field.field_delta_s == 0
        ).catalogue_future_equal_calendar_block_rms_hz
        for item in result.partitions
    ]
    axis.plot(labels, orbit, marker="o", label="Best training-ranked SGP4 candidate")
    for degree in (1, 2, 3):
        axis.plot(
            labels,
            [
                next(
                    score for score in item.radio_polynomial_null.scores if score.degree == degree
                ).evaluation_equal_calendar_block_rms_hz
                for item in result.partitions
            ],
            marker="o",
            label=f"Radio polynomial degree {degree}",
        )
    axis.set_title(f"{short}: frozen future equal-calendar-block RMS")
    axis.set_ylabel("RMS (Hz)")
    axis.tick_params(axis="x", rotation=18)
    axis.grid(alpha=0.25)
    axis.legend(fontsize=8)
    figure.savefig(comparison_path, dpi=160)
    plt.close(figure)
    return tau_path, comparison_path


def _render_report(
    amendment: dict[str, Any],
    results: tuple[LongArcDevelopmentRunResult, ...],
    artifact_dir: Path,
    report_path: Path,
) -> str:
    lines = [
        "# Opened Long-Arc Satellite Association Development Results",
        "",
        "This is opened-development evidence, not independent confirmation, a secure NORAD "
        "claim, or positioning validation. The `±500 s` fields are two descriptive "
        "wrong-epoch challenges; they are not a null distribution, p-value, or gate.",
        "",
        f"Execution amendment: `{amendment['amendment_id']}` (`{amendment['amendment_digest']}`).",
        "",
    ]
    for result in results:
        short = "9981" if "9981" in result.arc_id else "150802"
        main = result.partitions[0]
        true_field = next(item for item in main.field_scores if item.field_delta_s == 0)
        winner = next(
            item for item in true_field.association.scores if item.kind == "catalogue-candidate"
        )
        true_population = next(
            item.candidate_count for item in result.field_banks if item.field_delta_s == 0
        )
        persisted = winner.heldout_rank == 1 and not true_field.association.heldout_exact_tie
        abstentions = ", ".join(true_field.association.abstention_diagnostics) or "none"
        lines.extend(
            [
                f"## {short}",
                "",
                f"- Candidate population at true time: {true_population}.",
                "- Training-ranked candidate: "
                f"NORAD {winner.catalog_number}, tau {winner.selected_tau_s:+.2f} s.",
                "- Future equal-calendar-block RMS: "
                f"{true_field.catalogue_future_equal_calendar_block_rms_hz:.3f} Hz.",
                f"- Training winner persisted as heldout rank one: {persisted}.",
                "- Association abstention recommended: "
                f"{true_field.association.abstention_recommended} ({abstentions}).",
                f"- [Machine-readable result](figures/{artifact_dir.name}/{short}-result.json)",
                f"- [Tau profiles](figures/{artifact_dir.name}/{short}-main-tau-profiles.png)",
                "- [Future model comparison]"
                f"(figures/{artifact_dir.name}/{short}-future-model-comparison.png)",
                "",
            ]
        )
    lines.extend(
        [
            "## Claim boundary",
            "",
            "The observer is a reviewed preset rather than capture-bound authority; boresight "
            "is absent; both arcs were already opened for development; numeric thresholds are "
            "unset; and no independent recurrence is tested here. Therefore every candidate "
            "remains conditional development evidence.",
            "",
            f"Manifest: [manifest](figures/{artifact_dir.name}/manifest.json).",
            "",
        ]
    )
    if report_path.name not in str(report_path):
        raise LongArcExecutionAuthorityError("report path is invalid")
    return "\n".join(lines)


def _validate_base_protocol(root: Path, value: object) -> None:
    if not isinstance(value, dict) or set(value) != {
        "path",
        "sha256",
        "protocol_digest",
    }:
        raise LongArcExecutionAuthorityError("base protocol binding is malformed")
    path = _resolve_input(root, Path(value["path"]))
    if _sha256_file(path) != value["sha256"]:
        raise LongArcExecutionAuthorityError("base protocol bytes drifted")


def _validate_implementation(root: Path, value: object) -> None:
    if not isinstance(value, dict) or set(value) != {"commit", "tree", "file_sha256"}:
        raise LongArcExecutionAuthorityError("implementation binding is malformed")
    commit = value["commit"]
    tree = value["tree"]
    files = value["file_sha256"]
    if not isinstance(commit, str) or not isinstance(tree, str) or not isinstance(files, dict):
        raise LongArcExecutionAuthorityError("implementation binding types are invalid")
    head = _git(root, "rev-parse", "HEAD")
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, head],
        cwd=root,
        check=False,
        capture_output=True,
    ).returncode:
        raise LongArcExecutionAuthorityError("implementation commit is not an ancestor of HEAD")
    if _git(root, "rev-parse", f"{commit}^{{tree}}") != tree:
        raise LongArcExecutionAuthorityError("implementation tree binding differs")
    if tuple(sorted(files)) != _IMPLEMENTATION_FILES:
        raise LongArcExecutionAuthorityError("implementation file hash inventory is not exact")
    for relative, digest in files.items():
        if not isinstance(relative, str) or not isinstance(digest, str):
            raise LongArcExecutionAuthorityError("implementation file binding is malformed")
        if _sha256_file(_resolve_input(root, Path(relative))) != digest:
            raise LongArcExecutionAuthorityError(f"implementation file drifted: {relative}")
        if _git_blob_sha256(root, commit, relative) != digest:
            raise LongArcExecutionAuthorityError(
                f"implementation file is not bound to the implementation commit: {relative}"
            )


def _validate_raw_tle_inputs(value: object) -> None:
    if not isinstance(value, list) or len(value) != 2:
        raise LongArcExecutionAuthorityError("raw TLE input inventory must contain two arcs")
    expected = {
        "long-arc-9981-r19f2-s1-rx1-upper-0-30s",
        "long-arc-150802-r19f2-s1-rx1-upper-37p575-51p4s",
    }
    if {item.get("arc_id") for item in value if isinstance(item, dict)} != expected:
        raise LongArcExecutionAuthorityError("raw TLE arc inventory differs")
    for item in value:
        if not isinstance(item, dict) or set(item) != {
            "arc_id",
            "path",
            "sha256",
            "object_count",
        }:
            raise LongArcExecutionAuthorityError("raw TLE binding is malformed")
        path = Path(item["path"])
        if not path.is_absolute() or not path.is_file():
            raise LongArcExecutionAuthorityError("raw TLE path must be an existing absolute file")
        if _sha256_file(path) != item["sha256"] or item["object_count"] != 10972:
            raise LongArcExecutionAuthorityError("raw TLE digest or inventory differs")


def _validate_numerical_controls(value: object) -> None:
    expected = {
        "tau_lower_s": -5.0,
        "tau_upper_s": 5.0,
        "tau_step_s": 0.25,
        "tau_state_count": 41,
        "support_integration_sample_count": 5,
        "prediction_uncertainty_floor_hz": 1.0,
        "prediction_element_age_growth_hz_per_day": 0.0,
        "prediction_fit_residual_multiplier": 1.0,
        "prediction_maximum_propagated_states": 250000000,
        "population_coarse_spacing_s": 0.1,
        "population_maximum_coarse_time_count": 10000,
        "population_maximum_exact_time_count": 200000,
        "population_maximum_coarse_propagated_states": 10000000,
        "population_maximum_exact_propagated_states": 20000000,
        "maximum_candidate_count": 10000,
        "partition_rounding": "nearest-integer-half-up-v1",
    }
    if value != expected:
        raise LongArcExecutionAuthorityError("numerical controls differ from frozen V1")


def _validate_output_paths(root: Path, value: object) -> None:
    if not isinstance(value, dict) or set(value) != {
        "artifact_directory",
        "attempt_receipt_path",
        "report_path",
    }:
        raise LongArcExecutionAuthorityError("output binding is malformed")
    for relative in value.values():
        path = _resolve_new_output(root, relative)
        if path.exists():
            raise LongArcExecutionAuthorityError("exclusive output path already exists")


def _validate_claim_boundary(value: object) -> None:
    if value != {
        "opened_development_only": True,
        "secure_norad_permitted": False,
        "positioning_validation_permitted": False,
        "wrong_epoch_is_null_distribution": False,
        "wrong_epoch_is_gate": False,
        "numerical_thresholds_are_set": False,
        "new_rf_collection_authorized": False,
    }:
        raise LongArcExecutionAuthorityError("claim boundary differs")


def _load_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise LongArcExecutionAuthorityError("execution amendment must be a JSON object")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise LongArcExecutionAuthorityError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _resolve_input(root: Path, path: Path) -> Path:
    candidate = path if path.is_absolute() else root / path
    resolved = candidate.resolve()
    if not resolved.is_file():
        raise LongArcExecutionAuthorityError(f"required input is missing: {path}")
    return resolved


def _resolve_new_output(root: Path, relative: str | Path) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise LongArcExecutionAuthorityError("output path must be repository-relative")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise LongArcExecutionAuthorityError("output path escapes repository root") from error
    return resolved


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_json_exclusive(path: Path, value: object) -> None:
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    except FileExistsError as error:
        raise LongArcExecutionAuthorityError(
            "attempt receipt already exists; silent retry is forbidden"
        ) from error


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _git_blob_sha256(root: Path, commit: str, relative: str) -> str:
    value = subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    return _sha256_bytes(value)


def main() -> int:
    args = _parse_args()
    artifact_dir, report_path = execute_authorized_development_run(
        args.repository_root,
        args.execution_amendment,
    )
    print(f"artifacts={artifact_dir}")
    print(f"report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
