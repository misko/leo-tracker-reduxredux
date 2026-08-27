#!/usr/bin/env python3
"""Run the hash-authorized C1/C2/C3 opened-long-arc checkpoints once.

The tool is intentionally unusable without an additive execution amendment.
It authenticates the frozen protocol, operational roadmap, implementation,
sealed response-free receipts, exact TLE bytes, provisional calibration
authority, numerical controls, claim denials, and exclusive outputs before
doing scientific work.  The two arcs are processed and released strictly one
at a time; no IQ is opened and the +/-500 second catalogues remain descriptive.
"""

from __future__ import annotations

import argparse
import ctypes
import gc
import hashlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from contextlib import ExitStack, suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any, Literal, TextIO

import matplotlib
import zstandard as zstd

matplotlib.use("Agg", force=True)

import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.catalogue_observability import (  # noqa: E402
    CandidateObservabilityConfig,
    CandidateObservabilityResult,
    MeasurementFloorOverlay,
    ObservabilityWorkLimits,
    WrongFieldBankExpectation,
    analyze_candidate_observability,
    candidate_observability_result_payload,
)
from leo.analysis.catalogue_prediction import (  # noqa: E402
    ExactTauPolicy,
    Sgp4SupportPredictionPolicy,
    TauGridPoint,
)
from leo.analysis.research.block_predictive_evidence import (  # noqa: E402
    CalendarBlockCovariance,
)
from leo.analysis.research.catalogue_observability_figures import (  # noqa: E402
    CatalogueObservabilityFigureReceipt,
    render_catalogue_observability_figures,
)
from leo.analysis.research.compact_catalogue_prediction_bank import (  # noqa: E402
    open_compact_catalogue_prediction_array_bank_view,
)
from leo.analysis.research.long_arc_catalogue_adapter import (  # noqa: E402
    load_registered_long_arc_graph,
)
from leo.analysis.research.long_arc_hypothesis_closure import (  # noqa: E402
    LongArcHypothesisClosureConfig,
    LongArcHypothesisClosureResult,
    verify_long_arc_hypothesis_closure_result,
)
from leo.analysis.research.long_arc_observability_rebuild import (  # noqa: E402
    CompactFieldBankRebuildPolicy,
    iter_rebuilt_digest_identical_compact_field_banks,
    load_sealed_response_free_bank_inventory,
)
from leo.analysis.research.satellite_pnt_long_arc_protocol import (  # noqa: E402
    SatellitePntLongArcProtocolV1,
    load_satellite_pnt_long_arc_protocol,
)
from leo.analysis.research.satellite_tracking_checkpoint_runner import (  # noqa: E402
    LongArcBlockEvidenceDesign,
    LongArcBlockEvidenceRun,
    LongArcCatalogueConnectedNeighborhoodBinding,
    LongArcCatalogueConnectedNeighborhoodReceipt,
    close_long_arc_block_evidence_run,
    long_arc_block_evidence_run_payload,
    score_registered_long_arc_model_families,
    seal_long_arc_catalogue_connected_neighborhood_binding,
)
from leo.contracts.digests import (  # noqa: E402
    Sha256Digest,
    canonical_digest,
    canonical_json_bytes,
    sha256_digest,
)
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1  # noqa: E402

DEFAULT_AMENDMENT = Path(
    "config/analysis/satellite-tracking-checkpoints-execution-amendment-v1.json"
)

_EXPECTED_AMENDMENT_ID = "2026-08-27-satellite-tracking-checkpoints-opened-arcs-attempt1"
_EXPECTED_CHRONOLOGY = (
    "Frozen after the implementation commit and before the first C1/C2/C3 opened-arc execution."
)
_EXPECTED_OUTPUTS = {
    "artifact_directory": ("reports/figures/2026_08_27_satellite_tracking_checkpoints_v1"),
    "report_path": "reports/2026_08_27_satellite_tracking_checkpoint_results.md",
    "attempt_receipt_path": (
        "reports/figures/2026_08_27_satellite_tracking_checkpoints_v1-execution-receipt.json"
    ),
}

_SCHEMA = "org.leo.research.satellite-tracking-checkpoint-execution-amendment/v1"
_STATUS = "frozen-authority-for-one-opened-development-c1-c2-c3-attempt"
_RESULT_SCHEMA = "org.leo.research.satellite-tracking-checkpoint-arc-result/v1"
_MANIFEST_SCHEMA = "org.leo.research.satellite-tracking-checkpoint-manifest/v1"
_RECEIPT_SCHEMA = "org.leo.research.satellite-tracking-checkpoint-execution-receipt/v1"
_ALGORITHM_VERSION = "satellite-tracking-checkpoint-execution-v1"
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_OBJECT = re.compile(r"^[0-9a-f]{40}$")

_BASE_PROTOCOL_PATH = "config/analysis/satellite-pnt-long-arc-development-protocol-v1.json"
_BASE_PROTOCOL_SHA256 = "sha256:5959b3bbfef944576fc187ef132663ff653bb23d6b3d2b5f0980c654a183bce0"
_BASE_PROTOCOL_DIGEST = "sha256:2db143ac0a380ab4d673167bda9a88851eca26681123624c29ab7f64b1f64ecb"
_ROADMAP_PATH = "plans/satellite-tracking-next-checkpoints.md"
_ROADMAP_SHA256 = "sha256:7372c64de2194294f716af5f5da70d754efe48415894a300339fd8daf28db278"
_CALIBRATION_PROTOCOL_PATH = "config/analysis/satellite-pnt-cross-family-predictive-scoring-v2.json"
_CALIBRATION_PROTOCOL_SHA256 = (
    "sha256:e8b3f60e968e006a41bbdf1d9894d4b21571d0964cfdd16898101bbbd4256a9c"
)
_CALIBRATION_RESULT_PATH = (
    "reports/figures/2026_08_27_satellite_pnt_cross_family_predictive_scoring_attempt2.json"
)
_CALIBRATION_RESULT_SHA256 = (
    "sha256:02a430d186945b08e37e1b3f5b1925db6342ec59c4ef2f2d51135da69eb06b24"
)
_CALIBRATION_RESULT_DIGEST = (
    "sha256:1b857b6620ca4de26374f68c9024e4386250de649aace81c12c8d850ef8fec67"
)
_FLOOR_SOURCE_PATH = "reports/figures/2026_08_26_final_doppler_holdout_attempt2-score.json"
_FLOOR_SOURCE_SHA256 = "sha256:490f36345fec7d494261d63f3b3cf9581a249bdca46d80c8b9e63baed3471d1f"

_IMPLEMENTATION_FILES = (
    "src/leo/analysis/catalogue_observability.py",
    "src/leo/analysis/catalogue_prediction.py",
    "src/leo/analysis/catalogue_prediction_array_view.py",
    "src/leo/analysis/research/block_predictive_evidence.py",
    "src/leo/analysis/research/catalogue_observability_figures.py",
    "src/leo/analysis/research/compact_catalogue_prediction_bank.py",
    "src/leo/analysis/research/long_arc_catalogue_adapter.py",
    "src/leo/analysis/research/long_arc_hypothesis_closure.py",
    "src/leo/analysis/research/long_arc_observability_rebuild.py",
    "src/leo/analysis/research/satellite_pnt_long_arc_protocol.py",
    "src/leo/analysis/research/satellite_tracking_checkpoint_runner.py",
    "src/leo/contracts/catalogue_association.py",
    "src/leo/contracts/digests.py",
    "src/leo/contracts/sky.py",
    "tools/run_satellite_tracking_checkpoints.py",
)


@dataclass(frozen=True, slots=True)
class _ArcSpec:
    label: Literal["9981", "150802"]
    arc_id: str
    sealed_result_path: str
    sealed_result_sha256: Sha256Digest
    tle_default_path: str
    tle_sha256: Sha256Digest
    tle_collected_utc_ns: int
    tle_object_count: int
    annotation_catalog_numbers: tuple[int, ...]


_ARC_SPECS = (
    _ArcSpec(
        label="9981",
        arc_id="long-arc-9981-r19f2-s1-rx1-upper-0-30s",
        sealed_result_path=(
            "reports/figures/2026_08_27_satellite_pnt_long_arc_development_attempt2/"
            "9981-result.json.zst"
        ),
        sealed_result_sha256=(
            "sha256:ff7a442e241dc40081dda818942502a87e00049f3f2000bdd580a011448397bb"
        ),
        tle_default_path=(
            "/var/lib/leo/tle/archive/space-track/"
            "1787594647459418079-"
            "ac36512e603e6a21bc2ca16d0512a1e14db846ccbad9409d9ac601b371f16dee.tle"
        ),
        tle_sha256=("sha256:ac36512e603e6a21bc2ca16d0512a1e14db846ccbad9409d9ac601b371f16dee"),
        tle_collected_utc_ns=1_787_594_647_459_418_079,
        tle_object_count=10_972,
        annotation_catalog_numbers=(67_930,),
    ),
    _ArcSpec(
        label="150802",
        arc_id="long-arc-150802-r19f2-s1-rx1-upper-37p575-51p4s",
        sealed_result_path=(
            "reports/figures/2026_08_27_satellite_pnt_long_arc_development_attempt2/"
            "150802-result.json.zst"
        ),
        sealed_result_sha256=(
            "sha256:f63ea3b18fda0c34f5249a6db3da4b654c91ed6443d20c03dc132dae13361d02"
        ),
        tle_default_path=(
            "/var/lib/leo/tle/archive/space-track/"
            "1787666532658586719-"
            "9bb59fcf68fa36ce234ae9be79a492f0b92abc23bcf4f040bb5b64b61d3e31ad.tle"
        ),
        tle_sha256=("sha256:9bb59fcf68fa36ce234ae9be79a492f0b92abc23bcf4f040bb5b64b61d3e31ad"),
        tle_collected_utc_ns=1_787_666_532_658_586_719,
        tle_object_count=10_972,
        annotation_catalog_numbers=(59_748, 65_438),
    ),
)

_EXPECTED_CALIBRATION_AUTHORITY = {
    "protocol": {
        "path": _CALIBRATION_PROTOCOL_PATH,
        "sha256": _CALIBRATION_PROTOCOL_SHA256,
    },
    "sealed_result": {
        "path": _CALIBRATION_RESULT_PATH,
        "sha256": _CALIBRATION_RESULT_SHA256,
        "result_digest": _CALIBRATION_RESULT_DIGEST,
    },
    "independent_background_pair_count": 3,
    "formal_95_percent_rank_minimum_pairs": 19,
    "formal_95_percent_rank_pair_count_sufficient": False,
    "covariance_calibrated": False,
    "c2_complete": False,
}

_EXPECTED_NUMERICAL_CONTROLS: dict[str, Any] = {
    "prediction": {
        "tau_lower_s": -5.0,
        "tau_upper_s": 5.0,
        "tau_step_s": 0.25,
        "tau_state_count": 41,
        "support_integration_sample_count": 5,
        "standard_uncertainty_floor_hz": 1.0,
        "element_age_growth_hz_per_day": 0.0,
        "fit_residual_multiplier": 1.0,
        "maximum_propagated_states": 250_000_000,
    },
    "compact_rebuild": {
        "candidate_chunk_size": 8,
        "maximum_candidate_count": 1_024,
        "maximum_tau_count": 41,
        "maximum_observation_count": 2_048,
        "maximum_prediction_cells_per_field": 100_000_000,
        "maximum_array_storage_bytes_per_field": 2_000_000_000,
        "maximum_array_storage_bytes_total": 6_000_000_000,
    },
    "c1": {
        "drift_prior_sigma_hz_per_s": 20.0,
        "drift_reference_measurement_sigma_hz": 50.0,
        "close_pair_neighbours_per_candidate": 4,
        "numerical_negative_tolerance_hz2": 1e-6,
        "maximum_candidates_per_field": 1_024,
        "maximum_observations": 2_048,
        "maximum_tau_states": 41,
        "maximum_pair_prefix_evaluations": 1_500_000_000,
        "maximum_tau_prediction_cells": 100_000_000,
        "maximum_profiled_tau_pair_observation_evaluations": 200_000_000_000,
        "maximum_close_pair_count": 8_192,
        "maximum_rendered_pair_curves": 12,
        "measurement_floor_source": {
            "path": _FLOOR_SOURCE_PATH,
            "sha256": _FLOOR_SOURCE_SHA256,
        },
        "measurement_floor_overlays": [
            {
                "history_ms": 20.0,
                "floor_hz": 61.7472930318272,
                "source_digest": _FLOOR_SOURCE_SHA256,
                "calibrated": False,
            },
            {
                "history_ms": 125.0,
                "floor_hz": 57.75380979657822,
                "source_digest": _FLOOR_SOURCE_SHA256,
                "calibrated": False,
            },
            {
                "history_ms": 500.0,
                "floor_hz": 60.28885387873705,
                "source_digest": _FLOOR_SOURCE_SHA256,
                "calibrated": False,
            },
        ],
    },
    "c2": {
        "measurement_variance_scale": 1.0,
        "independent_variance_floor_hz2": 0.0,
        "block_common_variance_hz2": 2_500.0,
        "covariance_calibrated": False,
        "family_log_weights": [0.0, 0.0, 0.0],
        "training_block_fraction": 0.6,
        "calendar_block_duration_ns": 1_000_000_000,
        "receiver_offset_prior_sigma_hz": 1_000_000.0,
        "receiver_drift_prior_sigma_hz_per_s": 20.0,
        "radio_structural_parameter_prior_sigmas": [20_000.0, 2_000.0, 200.0],
        "minimum_usable_evaluation_observations": 2,
        "minimum_usable_evaluation_blocks": 2,
        "minimum_evaluation_observation_coverage": 1.0,
        "minimum_evaluation_block_coverage": 1.0,
        "maximum_hypothesis_count": 25_000,
        "maximum_state_observation_evaluations": 30_000_000,
    },
    "c3": {
        "credible_neighborhood_probability": 0.95,
        "singleton_minimum_within_candidate_probability": 0.95,
        "minimum_candidate_posterior_probability": 0.5,
        "maximum_outside_prior_mass_for_resolved_outcome": 0.0,
        "prior_normalization_tolerance": 1e-12,
        "maximum_hypotheses": 25_000,
        "maximum_blocks": 4_096,
        "maximum_score_cells": 1_000_000,
    },
    "persistence": {"zstandard_level": 10, "zstandard_threads": 0},
}

_EXPECTED_EXECUTION = {
    "authorized": True,
    "attempt_number": 1,
    "maximum_attempt_count": 1,
    "outputs_must_not_exist_before_execution": True,
    "new_rf_collection_authorized": False,
    "new_iq_read_authorized": False,
}

_EXPECTED_CLAIM_BOUNDARY = {
    "opened_development_only": True,
    "secure_norad_permitted": False,
    "positioning_validation_permitted": False,
    "wrong_epoch_is_null_distribution": False,
    "wrong_epoch_is_gate": False,
    "numerical_thresholds_are_set": False,
    "covariance_calibrated": False,
    "c2_complete": False,
    "posterior_probability_calibrated": False,
    "identity_claimed": False,
    "new_rf_collection_authorized": False,
    "new_iq_read_authorized": False,
}


class SatelliteTrackingCheckpointAuthorityError(ValueError):
    """The additive authority, input bytes, or output boundary failed closed."""


@dataclass(frozen=True, slots=True)
class AuthorizedCheckpointArc:
    label: str
    arc_id: str
    sealed_result_path: Path
    sealed_result_sha256: Sha256Digest
    tle_path: Path
    tle_sha256: Sha256Digest


@dataclass(frozen=True, slots=True)
class ValidatedCheckpointExecution:
    repository_root: Path
    amendment_path: Path
    amendment: dict[str, Any]
    arcs: tuple[AuthorizedCheckpointArc, AuthorizedCheckpointArc]
    artifact_directory: Path
    report_path: Path
    attempt_receipt_path: Path
    calibration_authority_digest: Sha256Digest


@dataclass(frozen=True, slots=True)
class _ArcPublishedReceipt:
    label: str
    arc_id: str
    result_file: str
    result_sha256: Sha256Digest
    result_byte_size: int
    c1_result_digest: Sha256Digest
    c2_result_digest: Sha256Digest
    c1_connected_neighborhood_binding_digest: Sha256Digest
    c3_result_digest: Sha256Digest
    figures: tuple[dict[str, Any], ...]
    summary: dict[str, Any]


def validate_checkpoint_execution_amendment(
    repository_root: Path,
    amendment_path: Path,
    *,
    tle_path_overrides: Mapping[str, Path] | None = None,
) -> ValidatedCheckpointExecution:
    """Authenticate the exact one-attempt authority before scientific work."""

    root = repository_root.resolve()
    path = _resolve_repository_input(root, amendment_path)
    canonical_amendment_path = _resolve_repository_input(root, DEFAULT_AMENDMENT)
    if path != canonical_amendment_path:
        raise SatelliteTrackingCheckpointAuthorityError(
            "execution amendment is not the canonical one-attempt authority"
        )
    amendment = _load_json_object(path)
    expected_keys = {
        "schema",
        "amendment_id",
        "status",
        "chronology",
        "base_protocol",
        "roadmap",
        "implementation",
        "sealed_results",
        "raw_tle_inputs",
        "calibration_authority",
        "numerical_controls",
        "outputs",
        "execution",
        "claim_boundary",
        "amendment_digest",
    }
    if set(amendment) != expected_keys or amendment.get("schema") != _SCHEMA:
        raise SatelliteTrackingCheckpointAuthorityError(
            "checkpoint execution amendment schema is not exact"
        )
    body = {key: value for key, value in amendment.items() if key != "amendment_digest"}
    if amendment.get("amendment_digest") != canonical_digest(body):
        raise SatelliteTrackingCheckpointAuthorityError(
            "checkpoint execution amendment semantic digest drifted"
        )
    if (
        amendment.get("status") != _STATUS
        or amendment.get("amendment_id") != _EXPECTED_AMENDMENT_ID
        or amendment.get("chronology") != _EXPECTED_CHRONOLOGY
        or not _exact_json_equal(amendment.get("execution"), _EXPECTED_EXECUTION)
    ):
        raise SatelliteTrackingCheckpointAuthorityError("execution authority is not exact")
    if not _exact_json_equal(amendment.get("claim_boundary"), _EXPECTED_CLAIM_BOUNDARY):
        raise SatelliteTrackingCheckpointAuthorityError("claim denials are not exact")

    _validate_base_protocol(root, amendment.get("base_protocol"))
    _validate_roadmap(root, amendment.get("roadmap"))
    _validate_implementation(root, amendment.get("implementation"))
    _validate_calibration_authority(root, amendment.get("calibration_authority"))
    if not _exact_json_equal(amendment.get("numerical_controls"), _EXPECTED_NUMERICAL_CONTROLS):
        raise SatelliteTrackingCheckpointAuthorityError("numerical controls are not exact")
    _validate_floor_source(root)

    sealed_by_arc = _validate_sealed_results(root, amendment.get("sealed_results"))
    tle_bindings = _validate_tle_bindings(amendment.get("raw_tle_inputs"))
    overrides = dict(tle_path_overrides or {})
    expected_override_keys = {item.arc_id for item in _ARC_SPECS}
    if not set(overrides) <= expected_override_keys:
        raise SatelliteTrackingCheckpointAuthorityError("TLE override names an unknown arc")

    arcs: list[AuthorizedCheckpointArc] = []
    for spec in _ARC_SPECS:
        raw_path = overrides.get(spec.arc_id, Path(tle_bindings[spec.arc_id]["path"]))
        tle_path = _resolve_external_input(root, raw_path)
        payload = _read_tle_bytes(tle_path)
        if sha256_digest(payload) != spec.tle_sha256:
            raise SatelliteTrackingCheckpointAuthorityError(
                f"TLE override or default bytes drifted for {spec.label}"
            )
        arcs.append(
            AuthorizedCheckpointArc(
                label=spec.label,
                arc_id=spec.arc_id,
                sealed_result_path=sealed_by_arc[spec.arc_id],
                sealed_result_sha256=spec.sealed_result_sha256,
                tle_path=tle_path,
                tle_sha256=spec.tle_sha256,
            )
        )

    artifact_directory, report_path, receipt_path = _validate_outputs(
        root, amendment.get("outputs")
    )
    return ValidatedCheckpointExecution(
        repository_root=root,
        amendment_path=path,
        amendment=amendment,
        arcs=(arcs[0], arcs[1]),
        artifact_directory=artifact_directory,
        report_path=report_path,
        attempt_receipt_path=receipt_path,
        calibration_authority_digest=canonical_digest(amendment["calibration_authority"]),
    )


def execute_authorized_checkpoints(
    repository_root: Path,
    amendment_path: Path,
    *,
    tle_path_overrides: Mapping[str, Path] | None = None,
) -> tuple[Path, Path, Path]:
    """Run both arcs sequentially and publish one exclusive checkpoint bundle."""

    _progress("preflight")
    authority = validate_checkpoint_execution_amendment(
        repository_root,
        amendment_path,
        tle_path_overrides=tle_path_overrides,
    )
    _progress("preflight-complete")
    authority.attempt_receipt_path.parent.mkdir(parents=True, exist_ok=True)
    authority.artifact_directory.parent.mkdir(parents=True, exist_ok=True)
    authority.report_path.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC).isoformat()
    receipt_base = {
        "schema": _RECEIPT_SCHEMA,
        "algorithm_version": _ALGORITHM_VERSION,
        "amendment_id": authority.amendment["amendment_id"],
        "amendment_digest": authority.amendment["amendment_digest"],
        "implementation_commit": authority.amendment["implementation"]["commit"],
        "repository_head_at_start": _git(authority.repository_root, "rev-parse", "HEAD"),
        "repository_tree_at_start": _git(authority.repository_root, "rev-parse", "HEAD^{tree}"),
        "attempt_number": 1,
        "started_utc": started,
        "new_rf_collection": False,
        "new_iq_read": False,
    }
    _write_json_exclusive(
        authority.attempt_receipt_path,
        {**receipt_base, "status": "running"},
    )
    stage_root: Path | None = None
    try:
        stage_root = Path(
            tempfile.mkdtemp(
                prefix=".satellite-tracking-checkpoints-",
                dir=authority.artifact_directory.parent,
            )
        )
        stage_artifacts = stage_root / "artifacts"
        stage_artifacts.mkdir()
        protocol_path = _resolve_repository_input(
            authority.repository_root,
            Path(authority.amendment["base_protocol"]["path"]),
        )
        protocol = load_satellite_pnt_long_arc_protocol(
            protocol_path,
            repository_root=authority.repository_root,
        )
        published: list[_ArcPublishedReceipt] = []
        for spec, arc in zip(_ARC_SPECS, authority.arcs, strict=True):
            published.append(
                _process_arc(
                    authority=authority,
                    protocol=protocol,
                    protocol_path=protocol_path,
                    spec=spec,
                    arc=arc,
                    stage_artifacts=stage_artifacts,
                )
            )
            gc.collect()

        _progress("serialization-render-complete")
        report_text = _render_report(authority, tuple(published))
        stage_report = stage_root / "report.md"
        _write_text_exclusive(stage_report, report_text)
        manifest_body = {
            "schema": _MANIFEST_SCHEMA,
            "algorithm_version": _ALGORITHM_VERSION,
            "amendment": {
                "path": authority.amendment_path.relative_to(authority.repository_root).as_posix(),
                "sha256": _sha256_file(authority.amendment_path),
                "semantic_digest": authority.amendment["amendment_digest"],
            },
            "base_protocol": authority.amendment["base_protocol"],
            "roadmap": authority.amendment["roadmap"],
            "implementation": authority.amendment["implementation"],
            "calibration_authority": authority.amendment["calibration_authority"],
            "arcs": [asdict(item) for item in published],
            "report": {
                "path": authority.report_path.relative_to(authority.repository_root).as_posix(),
                "sha256": _sha256_file(stage_report),
            },
            "claim_boundary": authority.amendment["claim_boundary"],
            "new_rf_collection": False,
            "new_iq_read": False,
            "c2_complete": False,
            "identity_claimed": False,
        }
        manifest = {
            **manifest_body,
            "manifest_digest": canonical_digest(manifest_body),
        }
        _write_json_exclusive(stage_artifacts / "manifest.json", manifest)
        _progress("publish")
        _publish_staged_outputs(
            stage_artifacts=stage_artifacts,
            artifact_directory=authority.artifact_directory,
            stage_report=stage_report,
            report_path=authority.report_path,
        )
        _progress("publish-complete")
    except BaseException as error:
        _write_json_atomic(
            authority.attempt_receipt_path,
            {
                **receipt_base,
                "status": "failed",
                "finished_utc": datetime.now(UTC).isoformat(),
                "exception_type": type(error).__name__,
                "exception_message": str(error),
            },
        )
        raise
    finally:
        if stage_root is not None:
            try:
                _remove_temporary_tree(stage_root)
            except SatelliteTrackingCheckpointAuthorityError as cleanup_error:
                _write_json_atomic(
                    authority.attempt_receipt_path,
                    {
                        **receipt_base,
                        "status": "failed",
                        "finished_utc": datetime.now(UTC).isoformat(),
                        "exception_type": type(cleanup_error).__name__,
                        "exception_message": str(cleanup_error),
                    },
                )
                raise

    _write_json_atomic(
        authority.attempt_receipt_path,
        {
            **receipt_base,
            "status": "complete",
            "finished_utc": datetime.now(UTC).isoformat(),
            "artifact_directory": authority.artifact_directory.relative_to(
                authority.repository_root
            ).as_posix(),
            "manifest_sha256": _sha256_file(authority.artifact_directory / "manifest.json"),
            "report_path": authority.report_path.relative_to(authority.repository_root).as_posix(),
            "report_sha256": _sha256_file(authority.report_path),
            "c2_complete": False,
            "identity_claimed": False,
        },
    )
    return (
        authority.artifact_directory,
        authority.report_path,
        authority.attempt_receipt_path,
    )


def _process_arc(
    *,
    authority: ValidatedCheckpointExecution,
    protocol: SatellitePntLongArcProtocolV1,
    protocol_path: Path,
    spec: _ArcSpec,
    arc: AuthorizedCheckpointArc,
    stage_artifacts: Path,
) -> _ArcPublishedReceipt:
    """Build, analyze, persist, render, summarize, and release one arc."""

    compact_storage = Path(
        tempfile.mkdtemp(
            prefix=f".{arc.label}-compact-banks-",
            dir=stage_artifacts.parent,
        )
    )
    try:
        return _process_arc_with_compact_storage(
            authority=authority,
            protocol=protocol,
            protocol_path=protocol_path,
            spec=spec,
            arc=arc,
            stage_artifacts=stage_artifacts,
            compact_storage=compact_storage,
        )
    finally:
        _remove_temporary_tree(compact_storage)


def _process_arc_with_compact_storage(
    *,
    authority: ValidatedCheckpointExecution,
    protocol: SatellitePntLongArcProtocolV1,
    protocol_path: Path,
    spec: _ArcSpec,
    arc: AuthorizedCheckpointArc,
    stage_artifacts: Path,
    compact_storage: Path,
) -> _ArcPublishedReceipt:
    """Execute one arc while compact mmap arrays remain available."""

    _progress("rebuild", arc.label)
    tle_payload = _read_tle_bytes(arc.tle_path)
    if sha256_digest(tle_payload) != arc.tle_sha256:
        raise SatelliteTrackingCheckpointAuthorityError(
            f"TLE bytes changed after preflight for {arc.label}"
        )
    bundle = load_registered_long_arc_graph(
        protocol_path,
        repository_root=authority.repository_root,
        arc_id=arc.arc_id,
    )
    inventory = load_sealed_response_free_bank_inventory(
        arc.sealed_result_path,
        expected_archive_sha256=arc.sealed_result_sha256,
    )
    observation = next(item for item in protocol.observations if item.arc_id == arc.arc_id)
    controls = authority.amendment["numerical_controls"]
    prediction_controls = controls["prediction"]
    tau_policy = _tau_policy(prediction_controls)
    prediction_policy = Sgp4SupportPredictionPolicy(
        integration_sample_count=prediction_controls["support_integration_sample_count"],
        standard_uncertainty_floor_hz=(prediction_controls["standard_uncertainty_floor_hz"]),
        element_age_growth_hz_per_day=(prediction_controls["element_age_growth_hz_per_day"]),
        fit_residual_multiplier=prediction_controls["fit_residual_multiplier"],
        maximum_propagated_states=prediction_controls["maximum_propagated_states"],
    )
    site = ObserverSiteV1(
        latitude_deg=protocol.observer.latitude_deg,
        longitude_deg=protocol.observer.longitude_deg,
        altitude_m=protocol.observer.altitude_m,
        label=protocol.observer.name,
    )
    tle_snapshot = TleSnapshotRefV1(
        provider=observation.tle_snapshot.provider,
        collected_utc_ns=observation.tle_snapshot.collected_utc_ns,
        digest=observation.tle_snapshot.raw_sha256,
        object_count=observation.tle_snapshot.object_count,
    )
    banks = tuple(
        iter_rebuilt_digest_identical_compact_field_banks(
            bundle.prediction_support,
            tle_payload,
            tle_snapshot=tle_snapshot,
            observer_site=site,
            nominal_rf_hz=protocol.models.nominal_rf_hz,
            selection_protocol_digest=protocol.protocol_digest,
            tau_policy=tau_policy,
            prediction_policy=prediction_policy,
            inventory=inventory,
            storage_directory=compact_storage,
            compact_policy=_compact_rebuild_policy(controls["compact_rebuild"]),
        )
    )
    if tuple(item.field_delta_s for item in banks) != (-500, 0, 500):
        raise SatelliteTrackingCheckpointAuthorityError(
            "rebuild did not return exact -500/0/+500 field banks"
        )
    minus_bank, true_bank, plus_bank = banks
    with ExitStack() as array_views:
        minus_view, true_view, plus_view = tuple(
            array_views.enter_context(open_compact_catalogue_prediction_array_bank_view(bank))
            for bank in banks
        )
        _progress("c1", arc.label)
        c1_result = analyze_candidate_observability(
            true_field_bank=true_view,
            wrong_field_banks=(minus_view, plus_view),
            config=_c1_config(true_bank, minus_bank, plus_bank, controls["c1"]),
        )
        _progress("c2", arc.label)
        c2_result = score_registered_long_arc_model_families(
            bundle.graph,
            true_view,
            design=_c2_design(
                controls["c2"],
                calibration_authority_digest=authority.calibration_authority_digest,
            ),
        )
    del minus_bank, true_bank, plus_bank, banks, inventory, tle_payload
    gc.collect()
    neighborhood_binding = _c1_connected_neighborhood_binding(c1_result, c2_result)
    del bundle
    gc.collect()
    _progress("c3", arc.label)
    c3_result = close_long_arc_block_evidence_run(
        c2_result,
        sequence_label=arc.arc_id,
        connected_neighborhood_binding=neighborhood_binding,
        closure_config=_c3_config(controls["c3"]),
    )
    verify_long_arc_hypothesis_closure_result(c3_result)

    _progress("serialization-render", arc.label)
    result_path = stage_artifacts / f"{arc.label}-checkpoint-result.json.zst"
    _write_arc_result_zst(
        result_path,
        arc=arc,
        c1_result=c1_result,
        c2_result=c2_result,
        connected_neighborhood_binding=neighborhood_binding,
        c3_result=c3_result,
        compression_controls=controls["persistence"],
    )
    c1_figures = render_catalogue_observability_figures(
        c1_result,
        output_directory=stage_artifacts,
        arc_label=arc.label,
        annotation_catalog_numbers=spec.annotation_catalog_numbers,
        maximum_pair_curves=controls["c1"]["maximum_rendered_pair_curves"],
    )
    c3_figure = _render_c3_figure(
        c3_result,
        path=stage_artifacts / f"{arc.label}-c3-family-connected-neighborhood-mass.png",
        arc_label=arc.label,
    )
    summary = _compact_arc_summary(c1_result, c2_result, c3_result, spec)
    figures = tuple(_figure_receipt_payload(item) for item in c1_figures) + (c3_figure,)
    return _ArcPublishedReceipt(
        label=arc.label,
        arc_id=arc.arc_id,
        result_file=result_path.name,
        result_sha256=_sha256_file(result_path),
        result_byte_size=result_path.stat().st_size,
        c1_result_digest=c1_result.content_digest,
        c2_result_digest=c2_result.content_digest,
        c1_connected_neighborhood_binding_digest=neighborhood_binding.content_digest,
        c3_result_digest=c3_result.result_digest,
        figures=figures,
        summary=summary,
    )


def _progress(phase: str, arc_label: str | None = None) -> None:
    scope = f" arc={arc_label}" if arc_label is not None else ""
    print(f"[satellite-checkpoints] phase={phase}{scope}", flush=True)


def _tau_policy(controls: Mapping[str, Any]) -> ExactTauPolicy:
    return ExactTauPolicy(
        policy="bounded-profile-minus5-plus5-v1",
        points=tuple(
            TauGridPoint(
                controls["tau_lower_s"] + index * controls["tau_step_s"],
                0.0,
            )
            for index in range(controls["tau_state_count"])
        ),
    )


def _c1_config(
    true_bank: Any,
    minus_bank: Any,
    plus_bank: Any,
    controls: Mapping[str, Any],
) -> CandidateObservabilityConfig:
    overlays = tuple(
        MeasurementFloorOverlay(
            history_ms=item["history_ms"],
            floor_hz=item["floor_hz"],
            source_digest=item["source_digest"],
            calibrated=False,
        )
        for item in controls["measurement_floor_overlays"]
    )
    return CandidateObservabilityConfig(
        expected_true_field_bank_digest=true_bank.content_digest,
        expected_wrong_field_banks=(
            WrongFieldBankExpectation(-500, minus_bank.content_digest),
            WrongFieldBankExpectation(500, plus_bank.content_digest),
        ),
        expected_support_digest=true_bank.support.content_digest,
        expected_tle_snapshot_digest=true_bank.tle_snapshot.digest,
        drift_prior_sigma_hz_per_s=controls["drift_prior_sigma_hz_per_s"],
        drift_reference_measurement_sigma_hz=(controls["drift_reference_measurement_sigma_hz"]),
        close_pair_neighbours_per_candidate=(controls["close_pair_neighbours_per_candidate"]),
        numerical_negative_tolerance_hz2=(controls["numerical_negative_tolerance_hz2"]),
        floor_overlays=overlays,
        work_limits=ObservabilityWorkLimits(
            maximum_candidates_per_field=controls["maximum_candidates_per_field"],
            maximum_observations=controls["maximum_observations"],
            maximum_tau_states=controls["maximum_tau_states"],
            maximum_pair_prefix_evaluations=(controls["maximum_pair_prefix_evaluations"]),
            maximum_tau_prediction_cells=controls["maximum_tau_prediction_cells"],
            maximum_profiled_tau_pair_observation_evaluations=(
                controls["maximum_profiled_tau_pair_observation_evaluations"]
            ),
            maximum_close_pair_count=controls["maximum_close_pair_count"],
        ),
    )


def _compact_rebuild_policy(
    controls: Mapping[str, Any],
) -> CompactFieldBankRebuildPolicy:
    return CompactFieldBankRebuildPolicy(
        candidate_chunk_size=controls["candidate_chunk_size"],
        maximum_candidate_count=controls["maximum_candidate_count"],
        maximum_tau_count=controls["maximum_tau_count"],
        maximum_observation_count=controls["maximum_observation_count"],
        maximum_prediction_cells_per_field=(controls["maximum_prediction_cells_per_field"]),
        maximum_array_storage_bytes_per_field=(controls["maximum_array_storage_bytes_per_field"]),
        maximum_array_storage_bytes_total=(controls["maximum_array_storage_bytes_total"]),
    )


def _c2_design(
    controls: Mapping[str, Any],
    *,
    calibration_authority_digest: Sha256Digest,
) -> LongArcBlockEvidenceDesign:
    receiver_prior_authority_digest = canonical_digest(
        {
            "schema": "org.leo.research.frozen-receiver-nuisance-prior/v1",
            "status": "frozen-provisional-development-assumptions",
            "receiver_offset_prior_sigma_hz": controls["receiver_offset_prior_sigma_hz"],
            "receiver_drift_prior_sigma_hz_per_s": controls["receiver_drift_prior_sigma_hz_per_s"],
            "parameters_calibrated": False,
            "source": "execution-amendment-numerical-controls-v1",
        }
    )
    return LongArcBlockEvidenceDesign(
        covariance=CalendarBlockCovariance(
            measurement_variance_scale=controls["measurement_variance_scale"],
            independent_variance_floor_hz2=(controls["independent_variance_floor_hz2"]),
            block_common_variance_hz2=controls["block_common_variance_hz2"],
            calibration_authority_digest=calibration_authority_digest,
            calibrated=False,
        ),
        receiver_nuisance_prior_authority_digest=receiver_prior_authority_digest,
        family_log_weights=tuple(controls["family_log_weights"]),
        training_block_fraction=controls["training_block_fraction"],
        calendar_block_duration_ns=controls["calendar_block_duration_ns"],
        receiver_offset_prior_sigma_hz=controls["receiver_offset_prior_sigma_hz"],
        receiver_drift_prior_sigma_hz_per_s=(controls["receiver_drift_prior_sigma_hz_per_s"]),
        radio_structural_parameter_prior_sigmas=tuple(
            controls["radio_structural_parameter_prior_sigmas"]
        ),
        minimum_usable_evaluation_observations=(controls["minimum_usable_evaluation_observations"]),
        minimum_usable_evaluation_blocks=controls["minimum_usable_evaluation_blocks"],
        minimum_evaluation_observation_coverage=(
            controls["minimum_evaluation_observation_coverage"]
        ),
        minimum_evaluation_block_coverage=(controls["minimum_evaluation_block_coverage"]),
        maximum_hypothesis_count=controls["maximum_hypothesis_count"],
        maximum_state_observation_evaluations=(controls["maximum_state_observation_evaluations"]),
    )


def _c3_config(controls: Mapping[str, Any]) -> LongArcHypothesisClosureConfig:
    return LongArcHypothesisClosureConfig(
        credible_neighborhood_probability=controls["credible_neighborhood_probability"],
        singleton_minimum_within_candidate_probability=(
            controls["singleton_minimum_within_candidate_probability"]
        ),
        minimum_candidate_posterior_probability=(
            controls["minimum_candidate_posterior_probability"]
        ),
        maximum_outside_prior_mass_for_resolved_outcome=(
            controls["maximum_outside_prior_mass_for_resolved_outcome"]
        ),
        prior_normalization_tolerance=controls["prior_normalization_tolerance"],
        maximum_hypotheses=controls["maximum_hypotheses"],
        maximum_blocks=controls["maximum_blocks"],
        maximum_score_cells=controls["maximum_score_cells"],
    )


def _c1_connected_neighborhood_binding(
    c1_result: CandidateObservabilityResult,
    c2_result: LongArcBlockEvidenceRun,
) -> LongArcCatalogueConnectedNeighborhoodBinding:
    atlas = c1_result.profiled_tau_candidate_identity_atlas
    if (
        atlas.true_field_prediction_bank_digest != c1_result.true_field_prediction_bank_digest
        or atlas.true_field_prediction_bank_digest != c2_result.prediction_bank_content_digest
        or atlas.candidate_numbers != c1_result.candidate_numbers
        or atlas.complete_tau_cross_product_evaluated is not True
        or atlas.nuisance_model != "offset-plus-ridge-drift-v1"
        or atlas.measured_response_accessed is not False
        or atlas.candidate_universe_selected_from_response is not False
        or atlas.identity_claimed is not False
    ):
        raise SatelliteTrackingCheckpointAuthorityError(
            "C1 profiled-tau atlas authority differs from C2"
        )
    matrix_count = len(atlas.tau_values_s) * (len(atlas.tau_values_s) + 1) // 2
    pair_observation_evaluations = (
        atlas.observation_count
        * len(atlas.candidate_numbers)
        * len(atlas.candidate_numbers)
        * matrix_count
    )
    if (
        atlas.tau_pair_distance_matrix_count != matrix_count
        or atlas.pair_observation_evaluations != pair_observation_evaluations
        or c1_result.work_receipt.profiled_tau_pair_distance_matrix_count != matrix_count
        or c1_result.work_receipt.profiled_tau_pair_observation_evaluations
        != pair_observation_evaluations
    ):
        raise SatelliteTrackingCheckpointAuthorityError(
            "C1 profiled-tau work receipt does not close"
        )
    overlays = tuple(item for item in atlas.floor_neighborhoods if item.history_ms == 125.0)
    if len(overlays) != 1:
        raise SatelliteTrackingCheckpointAuthorityError(
            "C1 must contain one exact 125 ms profiled-tau neighborhood"
        )
    overlay = overlays[0]
    if overlay.calibrated is not False or overlay.identity_gate_applied is not False:
        raise SatelliteTrackingCheckpointAuthorityError(
            "C1 profiled-tau neighborhood exceeds its descriptive authority"
        )
    by_catalogue: dict[int, Sha256Digest] = {}
    for component in overlay.final_components:
        component_id = canonical_digest(
            {
                "algorithm_version": ("c1-125ms-profiled-tau-drift-connected-neighborhood-v1"),
                "source_observability_result_digest": c1_result.content_digest,
                "source_profiled_tau_atlas_digest": atlas.content_digest,
                "history_ms": 125.0,
                "floor_hz": overlay.floor_hz,
                "source_digest": overlay.source_digest,
                "tau_values_s": atlas.tau_values_s,
                "tau_pairing_semantics": atlas.tau_pairing_semantics,
                "candidate_node_semantics": atlas.candidate_node_semantics,
                "threshold_graph_semantics": atlas.threshold_graph_semantics,
                "component_index": component.component_index,
                "catalog_numbers": component.catalog_numbers,
            }
        )
        for catalog_number in component.catalog_numbers:
            if catalog_number in by_catalogue:
                raise SatelliteTrackingCheckpointAuthorityError(
                    "C1 connected-neighborhood components overlap"
                )
            by_catalogue[catalog_number] = component_id
    if set(by_catalogue) != set(c1_result.candidate_numbers):
        raise SatelliteTrackingCheckpointAuthorityError(
            "C1 connected-neighborhood components do not cover the true catalogue"
        )
    receipts = tuple(
        LongArcCatalogueConnectedNeighborhoodReceipt(
            state_id=item.state_id,
            catalog_number=_required_int(item.catalog_number, "catalogue state number"),
            tau_s=_required_float(item.tau_s, "catalogue state tau"),
            connected_neighborhood_label=by_catalogue[
                _required_int(item.catalog_number, "catalogue state number")
            ],
        )
        for item in c2_result.state_receipts
        if item.state_kind == "catalogue"
    )
    return seal_long_arc_catalogue_connected_neighborhood_binding(
        source_observability_result_digest=c1_result.content_digest,
        source_profiled_tau_atlas_digest=atlas.content_digest,
        prediction_bank_content_digest=c2_result.prediction_bank_content_digest,
        c2_receiver_nuisance_basis_digest=c2_result.receiver_nuisance_basis_digest,
        tau_values_s=atlas.tau_values_s,
        nuisance_model=atlas.nuisance_model,
        drift_prior_sigma_hz_per_s=atlas.drift_prior_sigma_hz_per_s,
        reference_measurement_sigma_hz=atlas.reference_measurement_sigma_hz,
        floor_history_ms=overlay.history_ms,
        floor_hz=overlay.floor_hz,
        floor_source_digest=overlay.source_digest,
        floor_calibrated=overlay.calibrated,
        complete_tau_cross_product_evaluated=(atlas.complete_tau_cross_product_evaluated),
        tau_pairing_semantics=atlas.tau_pairing_semantics,
        candidate_node_semantics=atlas.candidate_node_semantics,
        threshold_graph_semantics=atlas.threshold_graph_semantics,
        identity_gate_applied=overlay.identity_gate_applied,
        receipts=receipts,
    )


def _write_arc_result_zst(
    path: Path,
    *,
    arc: AuthorizedCheckpointArc,
    c1_result: CandidateObservabilityResult,
    c2_result: LongArcBlockEvidenceRun,
    connected_neighborhood_binding: LongArcCatalogueConnectedNeighborhoodBinding,
    c3_result: LongArcHypothesisClosureResult,
    compression_controls: Mapping[str, Any],
) -> None:
    """Stream the complete JSON document without constructing a JSON string."""

    verify_long_arc_hypothesis_closure_result(c3_result)
    compressor = zstd.ZstdCompressor(
        level=compression_controls["zstandard_level"],
        threads=compression_controls["zstandard_threads"],
        write_checksum=True,
    )
    try:
        with (
            path.open("xb") as raw,
            compressor.stream_writer(raw, closefd=False) as compressed,
            io.TextIOWrapper(compressed, encoding="utf-8", write_through=True) as text,
        ):
            text.write("{")
            _stream_json_member(text, "algorithm_version", _ALGORITHM_VERSION, first=True)
            _stream_json_member(text, "arc_id", arc.arc_id)
            _stream_json_member(
                text,
                "c1_candidate_observability",
                candidate_observability_result_payload(c1_result),
            )
            _stream_json_member(
                text,
                "c1_connected_neighborhood_binding",
                asdict(connected_neighborhood_binding),
            )
            _stream_json_member(
                text,
                "c2_block_predictive_evidence",
                long_arc_block_evidence_run_payload(c2_result),
            )
            _stream_json_member(text, "c2_complete", False)
            _stream_json_member(
                text,
                "c3_hypothesis_closure",
                asdict(c3_result),
            )
            _stream_json_member(text, "identity_claimed", False)
            _stream_json_member(text, "schema", _RESULT_SCHEMA)
            _stream_json_member(text, "wrong_epoch_is_gate", False)
            text.write("}\n")
            text.flush()
    except OSError as error:
        raise SatelliteTrackingCheckpointAuthorityError(
            f"could not persist arc result exclusively: {path.name}"
        ) from error


def _stream_json_member(
    stream: TextIO,
    key: str,
    value: object,
    *,
    first: bool = False,
) -> None:
    if not first:
        stream.write(",")
    json.dump(key, stream, ensure_ascii=True)
    stream.write(":")
    json.dump(
        value,
        stream,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _render_c3_figure(
    result: LongArcHypothesisClosureResult,
    *,
    path: Path,
    arc_label: str,
) -> dict[str, Any]:
    verify_long_arc_hypothesis_closure_result(result)
    durations = [item.cumulative_duration_s for item in result.rolling_summaries]
    figure, (family_axis, neighborhood_axis) = plt.subplots(
        2,
        1,
        figsize=(9.4, 7.2),
        constrained_layout=True,
    )
    family_order = (
        "h0-radio-null",
        "h1-single-candidate",
        "h1-switch",
        "k2-two-candidate",
    )
    colors = ("#D55E00", "#0072B2", "#CC79A7", "#009E73")
    for family, color in zip(family_order, colors, strict=True):
        values = [
            next(
                item.posterior_probability
                for item in summary.family_posterior
                if item.family == family
            )
            for summary in result.rolling_summaries
        ]
        family_axis.plot(durations, values, label=family, color=color)
    final_summary = result.final_summary
    if final_summary.connected_neighborhood_summary_status != "available-final-prefix":
        raise SatelliteTrackingCheckpointAuthorityError(
            "C3 final connected-neighborhood summary is unavailable"
        )
    neighborhoods = tuple(
        sorted(
            (
                item
                for item in final_summary.connected_neighborhood_posterior
                if item.family == "h1-single-candidate"
            ),
            key=lambda item: item.connected_neighborhood_label,
        )
    )
    neighborhood_axis.scatter(
        range(len(neighborhoods)),
        [item.posterior_probability for item in neighborhoods],
        color="#4C78A8",
        alpha=0.7,
        edgecolors="none",
        s=10,
    )
    family_axis.set_ylabel("Conditional family mass")
    family_axis.set_xlabel("Cumulative evaluation duration (s)")
    family_axis.set_ylim(-0.02, 1.02)
    family_axis.legend(ncol=2, fontsize=7)
    family_axis.set_title(f"{arc_label}: provisional C3 cumulative posterior accounting")
    neighborhood_axis.set_xlabel("Canonical connected-neighborhood index")
    neighborhood_axis.set_ylabel("Final conditional mass")
    neighborhood_axis.set_ylim(-0.02, 1.02)
    neighborhood_axis.set_title("Final-prefix response-free connected-neighborhood mass spectrum")
    for axis in (family_axis, neighborhood_axis):
        axis.grid(True, alpha=0.22)
    neighborhood_axis.text(
        0.0,
        -0.25,
        "Rolling neighborhood maps are suppressed; final development mass is "
        "uncalibrated and makes no identity claim.",
        transform=neighborhood_axis.transAxes,
        fontsize=7,
        color="#555555",
    )
    buffer = io.BytesIO()
    try:
        figure.savefig(
            buffer,
            format="png",
            dpi=160,
            metadata={"Software": _ALGORITHM_VERSION},
        )
    finally:
        plt.close(figure)
    payload = buffer.getvalue()
    try:
        with path.open("xb") as output:
            output.write(payload)
    except OSError as error:
        raise SatelliteTrackingCheckpointAuthorityError(
            "could not publish C3 figure exclusively"
        ) from error
    body = {
        "figure_kind": "c3-family-connected-neighborhood-mass",
        "file_name": path.name,
        "sha256": sha256_digest(payload),
        "byte_size": len(payload),
        "source_result_digest": result.result_digest,
        "plotted_family_count": len(family_order),
        "plotted_candidate_connected_neighborhood_count": len(neighborhoods),
        "posterior_probability_calibrated": False,
        "identity_claimed": False,
        "algorithm_version": _ALGORITHM_VERSION,
    }
    return {**body, "content_digest": canonical_digest(body)}


def _compact_arc_summary(
    c1: CandidateObservabilityResult,
    c2: LongArcBlockEvidenceRun,
    c3: LongArcHypothesisClosureResult,
    spec: _ArcSpec,
) -> dict[str, Any]:
    drift_lane = c1.nuisance_geometries[1]
    if drift_lane.nuisance_model != "offset-plus-ridge-drift-v1":
        raise SatelliteTrackingCheckpointAuthorityError("C1 drift nuisance lane drifted")
    tau_zero_overlays = tuple(
        item for item in drift_lane.floor_overlays if item.history_ms == 125.0
    )
    if len(tau_zero_overlays) != 1:
        raise SatelliteTrackingCheckpointAuthorityError(
            "C1 must contain one exact 125 ms tau=0 drift overlay"
        )
    tau_zero_final_floor = tau_zero_overlays[0].prefix_summaries[-1]
    profiled_atlas = c1.profiled_tau_candidate_identity_atlas
    profiled_overlays = tuple(
        item for item in profiled_atlas.floor_neighborhoods if item.history_ms == 125.0
    )
    if (
        profiled_atlas.complete_tau_cross_product_evaluated is not True
        or profiled_atlas.nuisance_model != "offset-plus-ridge-drift-v1"
        or len(profiled_overlays) != 1
    ):
        raise SatelliteTrackingCheckpointAuthorityError(
            "C1 must contain one complete 125 ms profiled-tau drift neighborhood"
        )
    profiled_floor = profiled_overlays[0]
    component_by_catalogue = {
        number: component.catalog_numbers
        for component in profiled_floor.final_components
        for number in component.catalog_numbers
    }
    highlighted = {
        str(number): component_by_catalogue.get(number)
        for number in spec.annotation_catalog_numbers
    }
    top_states = tuple(
        {
            "catalog_numbers": item.catalog_numbers,
            "tau_s": item.tau_s,
            "posterior_probability": item.posterior_probability,
            "connected_neighborhood_label": item.connected_neighborhood_label,
        }
        for item in sorted(
            (
                item
                for item in c3.final_hypothesis_posterior
                if item.family == "h1-single-candidate"
            ),
            key=lambda item: (-item.posterior_probability, item.hypothesis_id),
        )[:5]
    )
    top_neighborhoods = tuple(
        {
            "catalog_numbers": item.catalog_numbers,
            "posterior_probability": item.posterior_probability,
            "within_candidate_probability": item.within_candidate_probability,
            "connected_neighborhood_label": item.connected_neighborhood_label,
        }
        for item in sorted(
            (
                item
                for item in c3.final_summary.connected_neighborhood_posterior
                if item.family == "h1-single-candidate"
            ),
            key=lambda item: (
                -item.posterior_probability,
                item.connected_neighborhood_label,
            ),
        )[:5]
    )
    wrong = {
        str(item.field_delta_s): {
            "final_minimum_nearest_any_rms_hz": (
                item.prefix_summaries[-1].minimum_nearest_any_rms_hz
            ),
            "final_median_nearest_any_rms_hz": (
                item.prefix_summaries[-1].median_nearest_any_rms_hz
            ),
            "observe_only": item.observe_only,
            "identity_gate_applied": item.identity_gate_applied,
            "true_field_tau_s": item.true_field_tau_s,
            "comparison_field_tau_s": item.comparison_field_tau_s,
            "tau_profiled": item.tau_profiled,
        }
        for item in c1.wrong_field_observability
    }
    outcome = c3.final_summary.outcome
    effective_neighborhood_count = c3.final_summary.effective_candidate_connected_neighborhood_count
    if outcome is None or effective_neighborhood_count is None:
        raise SatelliteTrackingCheckpointAuthorityError(
            "C3 final connected-neighborhood outcome is unavailable"
        )
    return {
        "observation_count": c1.work_receipt.observation_count,
        "true_candidate_count": c1.work_receipt.true_candidate_count,
        "tau_state_count": c1.work_receipt.tau_state_count,
        "c1_profiled_tau_pair_distance_matrix_count": (
            c1.work_receipt.profiled_tau_pair_distance_matrix_count
        ),
        "c1_profiled_tau_pair_observation_evaluations": (
            c1.work_receipt.profiled_tau_pair_observation_evaluations
        ),
        "c1_125ms_profiled_tau_final_component_count": profiled_floor.component_count,
        "c1_125ms_profiled_tau_final_largest_component_size": (
            profiled_floor.largest_component_size
        ),
        "c1_125ms_profiled_tau_final_singleton_component_count": (
            profiled_floor.singleton_component_count
        ),
        "c1_125ms_profiled_tau_final_edge_count": (profiled_floor.candidate_identity_edge_count),
        "c1_125ms_profiled_tau_final_median_local_candidate_count": (
            profiled_floor.median_local_candidate_count
        ),
        "c1_125ms_tau_zero_drift_final_median_local_candidate_count": (
            tau_zero_final_floor.median_local_candidate_count
        ),
        "c1_125ms_tau_zero_drift_final_median_soft_effective_candidate_count": (
            tau_zero_final_floor.median_soft_effective_candidate_count
        ),
        "highlighted_candidate_components": highlighted,
        "wrong_epoch_observe_only": wrong,
        "c2_covariance_calibrated": c2.evidence.covariance_parameters_calibrated,
        "c2_receiver_nuisance_parameters_calibrated": (c2.receiver_nuisance_parameters_calibrated),
        "c2_opportunity_inventory_complete": c2.evidence.opportunity_inventory_complete,
        "c2_missing_opportunities_retained": c2.evidence.missing_opportunities_retained,
        "c2_coverage_conditioned_on_observed_rows": (
            c2.evidence.coverage_conditioned_on_observed_rows
        ),
        "c2_complete": False,
        "c2_abstention_recommended": c2.evidence.abstention_recommended,
        "c2_abstention_diagnostics": c2.evidence.abstention_diagnostics,
        "c2_final_family_mass": {
            item.family: item.normalized_model_mass_final for item in c2.evidence.families
        },
        "c3_outcome": outcome.outcome,
        "c3_outcome_reason": outcome.reason,
        "c3_candidate_posterior_probability": outcome.candidate_posterior_probability,
        "c3_h0_radio_or_unassigned_posterior_probability": (
            outcome.h0_radio_or_unassigned_posterior_probability
        ),
        "c3_effective_candidate_connected_neighborhood_count": (effective_neighborhood_count),
        "c3_top_candidate_states": top_states,
        "c3_top_candidate_connected_neighborhoods": top_neighborhoods,
        "c3_optional_family_availability": tuple(
            asdict(item) for item in c3.optional_family_availability
        ),
        "posterior_probability_calibrated": False,
        "identity_claimed": False,
    }


def _render_report(
    authority: ValidatedCheckpointExecution,
    arcs: tuple[_ArcPublishedReceipt, ...],
) -> str:
    lines = [
        "# Satellite Tracking C1/C2/C3 Opened-Arc Checkpoints",
        "",
        "## Introduction and motivation",
        "",
        "This hash-authorized run asks whether the two registered POST-FIX long arcs "
        "contain enough response-free catalogue geometry and common-block predictive "
        "evidence to narrow satellite hypotheses. It is opened-development evidence, "
        "not independent confirmation.",
        "",
        "## Background",
        "",
        "Earlier opened-arc work recovered repeatable curvature, but short and similar "
        "Starlink Doppler arcs left multiple catalogue candidates close after a CFO offset "
        "was removed. C1 therefore measures catalogue geometry without response selection; "
        "C2 places orbit, radio-polynomial, and null states on common future blocks; C3 "
        "retains response-free connected neighborhoods rather than turning optimizer "
        "convergence into identity. These single-linkage neighborhoods are not cliques.",
        "",
        "## Authority and claim boundary",
        "",
        f"Execution amendment: `{authority.amendment['amendment_id']}` "
        f"(`{authority.amendment['amendment_digest']}`).",
        "",
        "The exact base protocol, operational roadmap, implementation commit/tree/files, "
        "two sealed result archives, two causal TLE snapshots, and all numerical controls "
        "were authenticated before analysis. No new RF was collected and no IQ was read.",
        "",
        "C2 remains incomplete: its authority has only 3 independent background pairs "
        "against the formal 19-pair rank floor. The covariance and all posterior masses "
        "remain explicitly uncalibrated. The registered graph does not provide a complete "
        "detector-opportunity universe, so coverage is conditioned on observed rows and C2 "
        "is forced to abstain. The +/-500 s fields are fixed at tau=0 in both fields, "
        "observe-only, and neither a null distribution nor an identity gate.",
        "",
        "## Methods",
        "",
        "For each arc, the tool parsed only the sealed leading response-free field-bank "
        "receipts, rebuilt digest-identical -500/0/+500 catalogue banks, computed causal "
        "C1 observability in an offset-only sensitivity lane and a receiver-basis-aligned "
        "offset-plus-ridge-drift principal lane, and overlaid the "
        "hash-bound 20/125/500 ms descriptive floors. It then scored the complete true-time "
        "catalogue-tau inventory and radio/null families on common chronological blocks. "
        "The final 125 ms C1 candidate-identity graph minimizes the "
        "offset-plus-ridge-drift separation over the complete cross-product of independently "
        "allowed tau states. Its response-free component label is then propagated across "
        "that candidate's bounded tau states before "
        "the C3 descriptive closure reducer was called. Rolling C3 neighborhood maps "
        "are deliberately suppressed; only the final-prefix map is summarized.",
        "",
        "The 20/125/500 ms overlays are detached holdout forecast-RMS sensitivity scales "
        "(61.747293, 57.753810, and 60.288854 Hz). They are not actual 20/125/500 ms "
        "reprocessing of either long arc and are not calibrated covariance estimates.",
        "The receiver and transmitter prior scales are frozen provisional development "
        "assumptions, not empirically calibrated nuisance distributions.",
        "",
        "## Results",
        "",
    ]
    for arc in arcs:
        summary = arc.summary
        wrong_minus = summary["wrong_epoch_observe_only"]["-500"]
        wrong_plus = summary["wrong_epoch_observe_only"]["500"]
        lines.extend(
            [
                f"### Arc {arc.label}",
                "",
                f"- Observations: {summary['observation_count']}; true-time candidates: "
                f"{summary['true_candidate_count']}; tau states per candidate: "
                f"{summary['tau_state_count']}.",
                f"- C1 125 ms fully tau-profiled drift-aware connected neighborhoods: "
                f"{summary['c1_125ms_profiled_tau_final_component_count']}; largest / "
                "singleton neighborhoods: "
                f"{summary['c1_125ms_profiled_tau_final_largest_component_size']} / "
                f"{summary['c1_125ms_profiled_tau_final_singleton_component_count']}; "
                "candidate-identity edges: "
                f"{summary['c1_125ms_profiled_tau_final_edge_count']}; median local "
                "candidate count: "
                f"{summary['c1_125ms_profiled_tau_final_median_local_candidate_count']:.3f}.",
                "- C1 exact tau-profile work: "
                f"{summary['c1_profiled_tau_pair_distance_matrix_count']} distance matrices / "
                f"{summary['c1_profiled_tau_pair_observation_evaluations']} "
                "pair-observation evaluations. The separately plotted tau=0 drift lane has "
                "median local / soft-effective candidate counts "
                f"{summary['c1_125ms_tau_zero_drift_final_median_local_candidate_count']:.3f} / "
                f"{summary['c1_125ms_tau_zero_drift_final_median_soft_effective_candidate_count']:.3f}.",
                f"- C1 -500 s nearest-curve final minimum/median RMS: "
                f"{wrong_minus['final_minimum_nearest_any_rms_hz']:.6f} / "
                f"{wrong_minus['final_median_nearest_any_rms_hz']:.6f} Hz "
                "(true tau=0 versus delta -500 s tau=0; observe only).",
                f"- C1 +500 s nearest-curve final minimum/median RMS: "
                f"{wrong_plus['final_minimum_nearest_any_rms_hz']:.6f} / "
                f"{wrong_plus['final_median_nearest_any_rms_hz']:.6f} Hz "
                "(true tau=0 versus delta +500 s tau=0; observe only).",
                *_highlighted_component_report_lines(summary),
                "- C2 opportunity coverage: incomplete universe; coverage is conditioned "
                "on observed rows; forced abstention diagnostics: "
                f"`{json.dumps(summary['c2_abstention_diagnostics'])}`.",
                f"- C2 final conditional family mass: "
                f"`{json.dumps(summary['c2_final_family_mass'], sort_keys=True)}`. "
                "These are not calibrated probabilities.",
                f"- C3 descriptive outcome: **{summary['c3_outcome']}** "
                f"(`{summary['c3_outcome_reason']}`); conditional candidate / H0 "
                "radio-or-unassigned mass: "
                f"{summary['c3_candidate_posterior_probability']:.6f} / "
                f"{summary['c3_h0_radio_or_unassigned_posterior_probability']:.6f}; "
                "effective candidate "
                "connected-neighborhood count: "
                f"{summary['c3_effective_candidate_connected_neighborhood_count']:.3f}.",
                *_top_state_report_lines(summary),
                f"- Full streamed result: `{arc.result_file}` (`{arc.result_sha256}`).",
                "",
                "Figures:",
                "",
                *(
                    f"![Arc {arc.label} {figure['figure_kind']}]"
                    f"({_report_relative_figure_path(authority, figure['file_name'])})"
                    for figure in arc.figures
                ),
                "",
            ]
        )
    lines.extend(
        [
            "## C0-C7 checkpoint decision table",
            "",
            "| Checkpoint | Decision after this run |",
            "|---|---|",
            (
                "| C0 — evidence authority | **Green.** Exact registered graphs, sealed "
                "archives, causal TLE bytes, and response-free bank digests were "
                "authenticated. |"
            ),
            (
                "| C1 — observability atlas | **Executed, provisional.** Prefix tau=0 "
                "geometry, fully tau-profiled drift-aware 125 ms candidate neighborhoods, "
                "tau sensitivity, and observe-only "
                "+/-500 s alternatives are reported; the detached floors are "
                "uncalibrated. |"
            ),
            (
                "| C2 — common evidence scale | **Incomplete (3/19).** Common-block "
                "development scores exist, but the independent-pair rank floor is not met "
                "and covariance is not calibrated; the incomplete opportunity inventory "
                "forces abstention. |"
            ),
            (
                "| C3 — long-arc closure | **Descriptive; unresolved overall.** Reducer "
                "outcomes are conditional on an evaluated, uncalibrated inventory and "
                "cannot promote identity. |"
            ),
            (
                "| C4 — causal multi-dwell | **Not run on real downstream evidence.** V2 "
                "staging mechanics are implemented, but no real causal multi-dwell "
                "filter/evidence execution is established here. |"
            ),
            (
                "| C5 — frozen correction replay | **Blocked.** No independent same-NORAD "
                "recurrence is available for no-refit replay. |"
            ),
            (
                "| C6 — blinded positioning | **Held behind C5.** No real-data positioning "
                "validation is authorized by these checkpoint outputs. |"
            ),
            (
                "| C7 — untouched confirmation | **Not authorized.** No new RF collection "
                "is authorized. |"
            ),
            "",
            "## Limitations",
            "",
            "The candidate and tau inventories are complete for the sealed fields, but the "
            "measurement overlays and C2 covariance are not calibrated for identity-set "
            "coverage, and the detector-opportunity universe is incomplete. H1-switch and "
            "K=2 are reported as structurally inapplicable when the frozen one-episode "
            "inventory contains no explicit states. The two arcs are opened development "
            "data, and wrong-epoch comparisons are not exchangeable nulls.",
            "The candidate-count and closest-pair figures are causal tau=0 sensitivity "
            "views. The C3 handoff instead uses the complete final-duration tau-profiled "
            "candidate graph; a prefix-by-prefix tau-profiled atlas remains future work.",
            "C3 `rolling_summaries` are cumulative prefixes of one fixed chronological "
            "training/evaluation partition. This run does not execute distinct "
            "rolling-origin refits or future scores, so that roadmap deliverable remains "
            "open.",
            "",
            "## Interpretation and next steps",
            "",
            "Every outcome is provisional and conditioned on the evaluated model inventory. "
            "A concentrated optimizer or posterior does not establish NORAD identity. The "
            "next decision is whether C1 indicates geometry-, measurement-, or calibration-"
            "limited ambiguity; C2 must reach its independent calibration floor before any "
            "C3 mass can support a gate. No positioning, transferable correction, or secure "
            "identity claim is made.",
            "",
        ]
    )
    return "\n".join(lines)


def _highlighted_component_report_lines(summary: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    for catalog_number, members in summary["highlighted_candidate_components"].items():
        if members is None:
            result.append(f"- Highlighted NORAD {catalog_number}: absent from the true field.")
            continue
        member_text = ", ".join(str(item) for item in members)
        result.append(
            f"- Highlighted NORAD {catalog_number}: 125 ms C1 connected-neighborhood size "
            f"{len(members)}, membership {{{member_text}}}."
        )
    return result


def _top_state_report_lines(summary: Mapping[str, Any]) -> list[str]:
    states = summary["c3_top_candidate_states"]
    neighborhoods = summary["c3_top_candidate_connected_neighborhoods"]
    result = ["- Top provisional C3 candidate states (not calibrated identity):"]
    if not states:
        result = ["- No evaluated C3 candidate state is available."]
    for state in states:
        catalog = "/".join(str(item) for item in state["catalog_numbers"])
        tau = "/".join(f"{item:g}" for item in state["tau_s"])
        result.append(
            f"  - NORAD {catalog}, tau {tau} s, conditional mass "
            f"{state['posterior_probability']:.8f}, connected neighborhood "
            f"`{state['connected_neighborhood_label']}`."
        )
    if not neighborhoods:
        result.append("- No final C3 candidate connected neighborhood is available.")
        return result
    result.append(
        "- Top provisional C3 connected neighborhoods (single-linkage, not calibrated identity):"
    )
    for neighborhood in neighborhoods:
        catalog = "/".join(str(item) for item in neighborhood["catalog_numbers"])
        within = neighborhood["within_candidate_probability"]
        within_text = "n/a" if within is None else f"{within:.8f}"
        result.append(
            f"  - NORAD set {catalog}, conditional total/within-candidate mass "
            f"{neighborhood['posterior_probability']:.8f} / {within_text}, connected "
            f"neighborhood `{neighborhood['connected_neighborhood_label']}`."
        )
    return result


def _report_relative_figure_path(
    authority: ValidatedCheckpointExecution,
    file_name: str,
) -> str:
    return Path(
        os.path.relpath(
            authority.artifact_directory / file_name,
            start=authority.report_path.parent,
        )
    ).as_posix()


def _validate_base_protocol(root: Path, value: object) -> None:
    expected = {
        "path": _BASE_PROTOCOL_PATH,
        "sha256": _BASE_PROTOCOL_SHA256,
        "protocol_digest": _BASE_PROTOCOL_DIGEST,
    }
    if not _exact_json_equal(value, expected):
        raise SatelliteTrackingCheckpointAuthorityError("base protocol binding differs")
    path = _resolve_repository_input(root, Path(_BASE_PROTOCOL_PATH))
    if _sha256_file(path) != _BASE_PROTOCOL_SHA256:
        raise SatelliteTrackingCheckpointAuthorityError("base protocol bytes drifted")
    document = _load_json_object(path)
    if document.get("protocol_digest") != _BASE_PROTOCOL_DIGEST:
        raise SatelliteTrackingCheckpointAuthorityError("base protocol digest differs")


def _validate_roadmap(root: Path, value: object) -> None:
    expected = {"path": _ROADMAP_PATH, "sha256": _ROADMAP_SHA256}
    if not _exact_json_equal(value, expected):
        raise SatelliteTrackingCheckpointAuthorityError("roadmap binding differs")
    if _sha256_file(_resolve_repository_input(root, Path(_ROADMAP_PATH))) != _ROADMAP_SHA256:
        raise SatelliteTrackingCheckpointAuthorityError("roadmap bytes drifted")


def _validate_implementation(root: Path, value: object) -> None:
    if not isinstance(value, dict) or set(value) != {
        "commit",
        "tree",
        "file_sha256",
        "runtime_environment",
    }:
        raise SatelliteTrackingCheckpointAuthorityError("implementation binding is malformed")
    commit = value["commit"]
    tree = value["tree"]
    file_sha256 = value["file_sha256"]
    runtime_environment = value["runtime_environment"]
    if (
        not isinstance(commit, str)
        or _GIT_OBJECT.fullmatch(commit) is None
        or not isinstance(tree, str)
        or _GIT_OBJECT.fullmatch(tree) is None
        or not isinstance(file_sha256, dict)
        or tuple(sorted(file_sha256)) != tuple(sorted(_IMPLEMENTATION_FILES))
    ):
        raise SatelliteTrackingCheckpointAuthorityError("implementation inventory is not exact")
    head = _git(root, "rev-parse", "HEAD")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, head],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if ancestor.returncode != 0:
        raise SatelliteTrackingCheckpointAuthorityError(
            "implementation commit is not an ancestor of HEAD"
        )
    if _git(root, "rev-parse", f"{commit}^{{tree}}") != tree:
        raise SatelliteTrackingCheckpointAuthorityError("implementation tree differs")
    canonical_amendment = DEFAULT_AMENDMENT.as_posix()
    changed_since_implementation = tuple(
        item for item in _git(root, "diff", "--name-only", f"{commit}..HEAD").splitlines() if item
    )
    if changed_since_implementation != (canonical_amendment,):
        raise SatelliteTrackingCheckpointAuthorityError(
            "repository changed outside the canonical execution amendment"
        )
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise SatelliteTrackingCheckpointAuthorityError(
            "checkpoint execution requires a clean worktree"
        )
    if not _exact_json_equal(runtime_environment, _runtime_environment(root)):
        raise SatelliteTrackingCheckpointAuthorityError("numerical runtime environment differs")
    for relative in _IMPLEMENTATION_FILES:
        digest = file_sha256.get(relative)
        if not _is_digest(digest):
            raise SatelliteTrackingCheckpointAuthorityError(
                f"implementation digest is malformed: {relative}"
            )
        working_path = _resolve_repository_input(root, Path(relative))
        if _sha256_file(working_path) != digest:
            raise SatelliteTrackingCheckpointAuthorityError(
                f"implementation working file drifted: {relative}"
            )
        if _git_blob_sha256(root, commit, relative) != digest:
            raise SatelliteTrackingCheckpointAuthorityError(
                f"implementation commit file differs: {relative}"
            )


def _validate_calibration_authority(root: Path, value: object) -> None:
    if not _exact_json_equal(value, _EXPECTED_CALIBRATION_AUTHORITY):
        raise SatelliteTrackingCheckpointAuthorityError("C2 calibration authority differs")
    protocol_path = _resolve_repository_input(root, Path(_CALIBRATION_PROTOCOL_PATH))
    result_path = _resolve_repository_input(root, Path(_CALIBRATION_RESULT_PATH))
    if _sha256_file(protocol_path) != _CALIBRATION_PROTOCOL_SHA256:
        raise SatelliteTrackingCheckpointAuthorityError("C2 calibration protocol drifted")
    if _sha256_file(result_path) != _CALIBRATION_RESULT_SHA256:
        raise SatelliteTrackingCheckpointAuthorityError("C2 calibration result drifted")
    protocol = _load_json_object(protocol_path)
    result = _load_json_object(result_path).get("result")
    if not isinstance(result, dict):
        raise SatelliteTrackingCheckpointAuthorityError("C2 calibration result is malformed")
    expected = (
        3,
        19,
        False,
        False,
        False,
        False,
        _CALIBRATION_RESULT_DIGEST,
    )
    observed = (
        protocol.get("input", {}).get("independent_background_pair_count")
        if isinstance(protocol.get("input"), dict)
        else None,
        protocol.get("calibration", {}).get("formal_95_percent_rank_minimum_pairs")
        if isinstance(protocol.get("calibration"), dict)
        else None,
        protocol.get("calibration", {}).get("formal_coverage_claimed")
        if isinstance(protocol.get("calibration"), dict)
        else None,
        result.get("formal_95_percent_rank_pair_count_sufficient"),
        result.get("identity_claimed"),
        result.get("threshold_fitted"),
        result.get("result_digest"),
    )
    if not _exact_json_equal(observed, expected):
        raise SatelliteTrackingCheckpointAuthorityError(
            "C2 calibration stop-boundary evidence differs"
        )


def _validate_floor_source(root: Path) -> None:
    path = _resolve_repository_input(root, Path(_FLOOR_SOURCE_PATH))
    if _sha256_file(path) != _FLOOR_SOURCE_SHA256:
        raise SatelliteTrackingCheckpointAuthorityError("measurement-floor source bytes drifted")


def _validate_sealed_results(root: Path, value: object) -> dict[str, Path]:
    expected = [
        {
            "arc_id": item.arc_id,
            "path": item.sealed_result_path,
            "sha256": item.sealed_result_sha256,
        }
        for item in _ARC_SPECS
    ]
    if not _exact_json_equal(value, expected):
        raise SatelliteTrackingCheckpointAuthorityError("sealed result inventory differs")
    result: dict[str, Path] = {}
    for spec in _ARC_SPECS:
        path = _resolve_repository_input(root, Path(spec.sealed_result_path))
        if _sha256_file(path) != spec.sealed_result_sha256:
            raise SatelliteTrackingCheckpointAuthorityError(
                f"sealed result archive drifted for {spec.label}"
            )
        result[spec.arc_id] = path
    return result


def _validate_tle_bindings(value: object) -> dict[str, dict[str, Any]]:
    expected = [
        {
            "arc_id": item.arc_id,
            "path": item.tle_default_path,
            "sha256": item.tle_sha256,
            "collected_utc_ns": item.tle_collected_utc_ns,
            "object_count": item.tle_object_count,
        }
        for item in _ARC_SPECS
    ]
    if not _exact_json_equal(value, expected):
        raise SatelliteTrackingCheckpointAuthorityError("raw TLE inventory differs")
    assert isinstance(value, list)
    return {str(item["arc_id"]): item for item in value if isinstance(item, dict)}


def _validate_outputs(root: Path, value: object) -> tuple[Path, Path, Path]:
    if not _exact_json_equal(value, _EXPECTED_OUTPUTS):
        raise SatelliteTrackingCheckpointAuthorityError("output inventory is not exact")
    assert isinstance(value, dict)
    artifact = _resolve_new_output(root, value["artifact_directory"])
    report = _resolve_new_output(root, value["report_path"])
    receipt = _resolve_new_output(root, value["attempt_receipt_path"])
    if (
        not artifact.relative_to(root).as_posix().startswith("reports/figures/")
        or not report.relative_to(root).as_posix().startswith("reports/")
        or report.suffix != ".md"
        or not receipt.relative_to(root).as_posix().startswith("reports/figures/")
        or receipt.suffix != ".json"
        or len({artifact, report, receipt}) != 3
        or report.is_relative_to(artifact)
        or receipt.is_relative_to(artifact)
    ):
        raise SatelliteTrackingCheckpointAuthorityError("output paths exceed their scope")
    return artifact, report, receipt


def _publish_staged_outputs(
    *,
    stage_artifacts: Path,
    artifact_directory: Path,
    stage_report: Path,
    report_path: Path,
) -> None:
    if artifact_directory.exists() or report_path.exists():
        raise SatelliteTrackingCheckpointAuthorityError(
            "exclusive output path appeared during execution"
        )
    staged_inventory = _directory_inode_inventory(stage_artifacts)
    artifact_published = False
    report_created = False
    try:
        _rename_directory_no_replace(stage_artifacts, artifact_directory)
        artifact_published = True
        os.link(stage_report, report_path)
        report_created = True
        _fsync_directory(artifact_directory)
        _fsync_directory(artifact_directory.parent)
        _fsync_directory(report_path.parent)
    except BaseException as error:
        rollback_errors: list[BaseException] = []
        if not artifact_published and not stage_artifacts.exists() and artifact_directory.exists():
            try:
                artifact_published = (
                    _directory_inode_inventory(artifact_directory) == staged_inventory
                )
            except BaseException as ownership_error:
                rollback_errors.append(ownership_error)
        if report_created:
            try:
                if report_path.exists() and os.path.samefile(stage_report, report_path):
                    report_path.unlink()
            except BaseException as rollback_error:
                rollback_errors.append(rollback_error)
        if artifact_published:
            try:
                if _directory_inode_inventory(artifact_directory) != staged_inventory:
                    raise SatelliteTrackingCheckpointAuthorityError(
                        "published artifact ownership changed before rollback"
                    )
                _rename_directory_no_replace(artifact_directory, stage_artifacts)
            except BaseException as rollback_error:
                rollback_errors.append(rollback_error)
        if rollback_errors:
            raise SatelliteTrackingCheckpointAuthorityError(
                "checkpoint publication failed and rollback was incomplete"
            ) from rollback_errors[0]
        if not isinstance(error, (OSError, SatelliteTrackingCheckpointAuthorityError)):
            raise
        raise SatelliteTrackingCheckpointAuthorityError(
            "could not publish staged checkpoint outputs"
        ) from error


def _directory_inode_inventory(path: Path) -> tuple[tuple[str, int, int], ...]:
    try:
        entries = tuple(sorted(path.iterdir(), key=lambda item: item.name))
        if not entries or any(not item.is_file() or item.is_symlink() for item in entries):
            raise SatelliteTrackingCheckpointAuthorityError(
                "staged artifact inventory is not a nonempty flat regular-file bundle"
            )
        return tuple((item.name, item.stat().st_dev, item.stat().st_ino) for item in entries)
    except OSError as error:
        raise SatelliteTrackingCheckpointAuthorityError(
            "checkpoint artifact inventory is unreadable"
        ) from error


def _rename_directory_no_replace(source: Path, destination: Path) -> None:
    """Atomically publish one Linux directory without replacing a destination."""

    libc = ctypes.CDLL(None, use_errno=True)
    try:
        renameat2 = libc.renameat2
    except AttributeError as error:
        raise SatelliteTrackingCheckpointAuthorityError(
            "atomic no-replace directory publication is unavailable"
        ) from error
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    at_fdcwd = -100
    rename_noreplace = 1
    result = renameat2(
        at_fdcwd,
        os.fsencode(source),
        at_fdcwd,
        os.fsencode(destination),
        rename_noreplace,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number), destination)


def _figure_receipt_payload(
    value: CatalogueObservabilityFigureReceipt,
) -> dict[str, Any]:
    return asdict(value)


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SatelliteTrackingCheckpointAuthorityError(
            f"JSON authority is unreadable: {path}"
        ) from error
    if not isinstance(value, dict):
        raise SatelliteTrackingCheckpointAuthorityError("JSON authority must be an object")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SatelliteTrackingCheckpointAuthorityError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _resolve_repository_input(root: Path, value: Path) -> Path:
    path = value if value.is_absolute() else root / value
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise SatelliteTrackingCheckpointAuthorityError("repository input escapes its root")
    if not resolved.is_file():
        raise SatelliteTrackingCheckpointAuthorityError("repository input is not a file")
    return resolved


def _resolve_external_input(root: Path, value: Path) -> Path:
    if value.is_absolute():
        # The sealed archive directory is intentionally not traversable by the
        # service account.  Preserve its normalized absolute spelling so the
        # subsequent authenticated reader can use noninteractive sudo.
        return Path(os.path.abspath(value))
    path = root / value
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise SatelliteTrackingCheckpointAuthorityError("external input is unavailable") from error


def _resolve_new_output(root: Path, value: object) -> Path:
    if not isinstance(value, str):
        raise SatelliteTrackingCheckpointAuthorityError("output path must be text")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise SatelliteTrackingCheckpointAuthorityError("output path must be repository-relative")
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or path.exists():
        raise SatelliteTrackingCheckpointAuthorityError(
            "exclusive output path already exists or escapes root"
        )
    return path


def _read_tle_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except PermissionError:
        completed = subprocess.run(
            ["sudo", "-n", "--", "cat", path.as_posix()],
            check=False,
            capture_output=True,
        )
        if completed.returncode == 0:
            return completed.stdout
        raise SatelliteTrackingCheckpointAuthorityError(
            "TLE bytes are unreadable directly and via noninteractive sudo"
        ) from None
    except OSError as error:
        raise SatelliteTrackingCheckpointAuthorityError("TLE bytes are unreadable") from error


def _sha256_file(path: Path) -> Sha256Digest:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise SatelliteTrackingCheckpointAuthorityError(
            f"bound input is unreadable: {path}"
        ) from error
    return f"sha256:{digest.hexdigest()}"


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as error:
        raise SatelliteTrackingCheckpointAuthorityError("git authority query failed") from error


def _git_blob_sha256(root: Path, commit: str, relative: str) -> Sha256Digest:
    try:
        payload = subprocess.run(
            ["git", "show", f"{commit}:{relative}"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
    except subprocess.CalledProcessError as error:
        raise SatelliteTrackingCheckpointAuthorityError(
            f"implementation commit lacks file: {relative}"
        ) from error
    return sha256_digest(payload)


def _runtime_environment(root: Path) -> dict[str, object]:
    package_names = ("matplotlib", "numpy", "pydantic", "sgp4", "zstandard")
    try:
        package_versions = {name: metadata.version(name) for name in package_names}
    except metadata.PackageNotFoundError as error:
        raise SatelliteTrackingCheckpointAuthorityError(
            "required numerical runtime package metadata is unavailable"
        ) from error
    return {
        "python_version": platform.python_version(),
        "package_versions": package_versions,
        "uv_lock_sha256": _sha256_file(_resolve_repository_input(root, Path("uv.lock"))),
    }


def _json_output_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _write_json_atomic(path: Path, value: object) -> None:
    payload = _json_output_bytes(value)
    descriptor = -1
    temporary_path: Path | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(raw_path)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
        _fsync_directory(path.parent)
    except OSError as error:
        raise SatelliteTrackingCheckpointAuthorityError(
            f"atomic JSON output is unavailable: {path.name}"
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_path is not None:
            with suppress(FileNotFoundError):
                temporary_path.unlink()


def _write_json_exclusive(path: Path, value: object) -> None:
    payload = _json_output_bytes(value)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_directory(path.parent)
    except OSError as error:
        raise SatelliteTrackingCheckpointAuthorityError(
            f"exclusive JSON output already exists or is unavailable: {path.name}"
        ) from error


def _write_text_exclusive(path: Path, value: str) -> None:
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise SatelliteTrackingCheckpointAuthorityError(
            f"exclusive text output already exists or is unavailable: {path.name}"
        ) from error


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _remove_temporary_tree(path: Path) -> None:
    try:
        if path.exists():
            shutil.rmtree(path)
    except OSError as error:
        raise SatelliteTrackingCheckpointAuthorityError(
            f"temporary checkpoint storage could not be removed: {path.name}"
        ) from error
    if path.exists():
        raise SatelliteTrackingCheckpointAuthorityError(
            f"temporary checkpoint storage remains after cleanup: {path.name}"
        )


def _exact_json_equal(left: object, right: object) -> bool:
    try:
        return canonical_json_bytes(left) == canonical_json_bytes(right)
    except (TypeError, ValueError):
        return False


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _required_int(value: int | None, label: str) -> int:
    if value is None:
        raise SatelliteTrackingCheckpointAuthorityError(f"{label} is missing")
    return value


def _required_float(value: float | None, label: str) -> float:
    if value is None:
        raise SatelliteTrackingCheckpointAuthorityError(f"{label} is missing")
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--execution-amendment", type=Path, default=DEFAULT_AMENDMENT)
    parser.add_argument("--tle-9981", type=Path)
    parser.add_argument("--tle-150802", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    overrides = {
        spec.arc_id: value
        for spec, value in zip(
            _ARC_SPECS,
            (args.tle_9981, args.tle_150802),
            strict=True,
        )
        if value is not None
    }
    artifact_directory, report_path, receipt_path = execute_authorized_checkpoints(
        args.repository_root,
        args.execution_amendment,
        tle_path_overrides=overrides,
    )
    print(
        json.dumps(
            {
                "artifact_directory": artifact_directory.as_posix(),
                "report_path": report_path.as_posix(),
                "attempt_receipt_path": receipt_path.as_posix(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
