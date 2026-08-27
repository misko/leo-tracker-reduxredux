"""Strict loader for paired orbit/radio known-truth injection development."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from leo.analysis.research.doppler_dataset_policy import DopplerDatasetPolicy
from leo.analysis.research.polynomial_injection_protocol import (
    BackgroundSpan,
    PolynomialInjectionProtocol,
    load_polynomial_injection_protocol,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.sky import ObserverSiteV1

SCHEMA = "org.leo.research.satellite-pnt-cross-family-injection/v1"
_STATUS = "frozen-known-truth-development-no-execution"
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_TOP_LEVEL_KEYS = {
    "schema",
    "protocol_status",
    "authority",
    "observer",
    "signal_and_measurement",
    "selection",
    "pairs",
    "scoring",
    "interpretation_limits",
    "execution",
    "protocol_digest",
}
_PAIR_KEYS = {
    "pair_id",
    "background_session_id",
    "sample_zero_utc_ns",
    "span_start_utc_ns",
    "span_centre_utc_ns",
    "seed",
    "orbit_scenario_id",
    "radio_scenario_id",
    "tle_snapshot_path",
    "tle_snapshot_sha256",
    "tle_collected_utc_ns",
    "tle_object_count",
    "true_catalog_number",
    "true_object_name",
    "true_element_digest",
    "true_element_epoch_utc_ns",
    "centre_elevation_deg",
}


@dataclass(frozen=True, slots=True)
class CrossFamilyTruthPair:
    """One hard-null background with paired orbit and radio truth arms."""

    pair_id: str
    background_session_id: str
    sample_zero_utc_ns: int
    span_start_utc_ns: int
    span_centre_utc_ns: int
    seed: int
    orbit_scenario_id: str
    radio_scenario_id: str
    tle_snapshot_path: Path
    tle_snapshot_sha256: str
    tle_collected_utc_ns: int
    tle_object_count: int
    true_catalog_number: int
    true_object_name: str
    true_element_digest: str
    true_element_epoch_utc_ns: int
    centre_elevation_deg: float


@dataclass(frozen=True, slots=True)
class CrossFamilyInjectionProtocol:
    """Validated response-free design; loading it never reads IQ or TLE bytes."""

    protocol_digest: str
    dataset_policy_path: Path
    dataset_policy_sha256: str
    base_protocol_path: Path
    base_protocol_sha256: str
    base_protocol: PolynomialInjectionProtocol
    observer_site: ObserverSiteV1
    nominal_rf_hz: float
    snr_db: float
    frame_occupancy: float
    interpolation_spacing_s: float
    interpolation_maximum_error_hz: float
    pairs: tuple[CrossFamilyTruthPair, ...]
    training_fraction: float
    future_fraction: float

    def background(self, session_id: str) -> BackgroundSpan:
        return self.base_protocol.background(session_id)


def load_cross_family_injection_protocol(
    path: Path,
    *,
    dataset_policy: DopplerDatasetPolicy,
    repository_root: Path,
) -> CrossFamilyInjectionProtocol:
    """Load and close the exact paired known-truth development design."""

    root = _mapping(json.loads(path.read_text(encoding="utf-8")), "protocol")
    _exact_keys(root, _TOP_LEVEL_KEYS, "protocol")
    if root["schema"] != SCHEMA or root["protocol_status"] != _STATUS:
        raise ValueError("cross-family protocol schema or status differs from v1")
    protocol_digest = _digest(root["protocol_digest"], "protocol_digest")
    digest_payload = dict(root)
    del digest_payload["protocol_digest"]
    if canonical_digest(digest_payload) != protocol_digest:
        raise ValueError("cross-family protocol digest does not match content")

    authority = _mapping(root["authority"], "authority")
    _exact_keys(
        authority,
        {
            "dataset_policy_path",
            "dataset_policy_sha256",
            "experiment_role",
            "base_background_protocol_path",
            "base_background_protocol_sha256",
            "dynamic_discovery_forbidden",
            "background_or_span_substitution_forbidden",
            "active_backgrounds_forbidden",
        },
        "authority",
    )
    if authority["experiment_role"] != "polynomial_injection":
        raise ValueError("cross-family protocol must use the polynomial-injection role")
    for flag in (
        "dynamic_discovery_forbidden",
        "background_or_span_substitution_forbidden",
        "active_backgrounds_forbidden",
    ):
        if authority[flag] is not True:
            raise ValueError(f"authority must freeze {flag}")
    dataset_policy_path = _repository_path(
        authority["dataset_policy_path"], repository_root, "dataset policy"
    )
    dataset_policy_sha256 = _digest(authority["dataset_policy_sha256"], "dataset policy digest")
    if _file_digest(dataset_policy_path) != dataset_policy_sha256:
        raise ValueError("dataset policy bytes differ from cross-family authority")
    base_protocol_path = _repository_path(
        authority["base_background_protocol_path"], repository_root, "base protocol"
    )
    base_protocol_sha256 = _digest(
        authority["base_background_protocol_sha256"], "base protocol digest"
    )
    if _file_digest(base_protocol_path) != base_protocol_sha256:
        raise ValueError("base background protocol bytes differ from authority")
    base_protocol = load_polynomial_injection_protocol(
        base_protocol_path,
        dataset_policy=dataset_policy,
        repository_root=repository_root,
    )

    observer = _mapping(root["observer"], "observer")
    _exact_keys(
        observer,
        {
            "label",
            "latitude_deg",
            "longitude_deg",
            "altitude_m",
            "capture_bound",
            "position_uncertainty_m",
        },
        "observer",
    )
    if observer["capture_bound"] is not False or observer["position_uncertainty_m"] != 50.0:
        raise ValueError("observer must remain the reviewed non-capture-bound 50 m preset")
    observer_site = ObserverSiteV1(
        label=_string(observer["label"], "observer label"),
        latitude_deg=_finite_float(observer["latitude_deg"], "observer latitude"),
        longitude_deg=_finite_float(observer["longitude_deg"], "observer longitude"),
        altitude_m=_finite_float(observer["altitude_m"], "observer altitude"),
    )

    signal = _mapping(root["signal_and_measurement"], "signal_and_measurement")
    _exact_keys(
        signal,
        {
            "nominal_rf_hz",
            "sample_rate_hz",
            "duration_s",
            "frame_rate_hz",
            "frame_count",
            "template_edge",
            "template_sample_count",
            "template_sha256",
            "snr_db",
            "frame_occupancy",
            "frame_cfo_search_half_width_hz",
            "profile_step_hz",
            "minimum_exact_coherence",
            "minimum_coherence_margin",
            "orbit_truth_interpolation_spacing_s",
            "orbit_truth_interpolation_maximum_error_hz",
            "orbit_truth_tau_s",
            "sample_clock_offset_ppm",
            "radio_truth_rule",
        },
        "signal_and_measurement",
    )
    expected_signal = {
        "sample_rate_hz": 2_500_000,
        "duration_s": base_protocol.duration_s,
        "frame_rate_hz": 750,
        "frame_count": base_protocol.frame_count,
        "template_edge": "lower",
        "template_sample_count": 3_333,
        "template_sha256": (
            "sha256:15455635bcdcfe0747f686ae317d235b5dfa54ae49c76b9741e6acc889d8a657"
        ),
        "frame_cfo_search_half_width_hz": base_protocol.frame_cfo_search_half_width_hz,
        "profile_step_hz": base_protocol.profile_step_hz,
        "minimum_exact_coherence": base_protocol.minimum_exact_coherence,
        "minimum_coherence_margin": base_protocol.minimum_coherence_margin,
        "orbit_truth_tau_s": 0.0,
        "sample_clock_offset_ppm": 0.0,
        "radio_truth_rule": "linear-match-orbit-cfo-and-rate-at-span-centre-v1",
    }
    if any(signal[key] != value for key, value in expected_signal.items()):
        raise ValueError("cross-family signal geometry differs from the frozen base")
    nominal_rf_hz = _positive_float(signal["nominal_rf_hz"], "nominal RF")
    snr_db = _finite_float(signal["snr_db"], "SNR")
    frame_occupancy = _finite_float(signal["frame_occupancy"], "frame occupancy")
    if snr_db != -16.0 or frame_occupancy != 1.0:
        raise ValueError("v1 truth arms require -16 dB and complete frame occupancy")
    interpolation_spacing_s = _positive_float(
        signal["orbit_truth_interpolation_spacing_s"], "interpolation spacing"
    )
    interpolation_maximum_error_hz = _positive_float(
        signal["orbit_truth_interpolation_maximum_error_hz"], "interpolation error"
    )
    if interpolation_spacing_s != 0.001 or interpolation_maximum_error_hz != 0.01:
        raise ValueError("orbit interpolation policy differs from v1")

    selection = _mapping(root["selection"], "selection")
    _exact_keys(
        selection,
        {
            "rule",
            "minimum_elevation_deg",
            "tie_break",
            "response_accessed",
            "candidate_population_for_scoring",
            "candidate_truncation_permitted",
        },
        "selection",
    )
    if selection != {
        "rule": "highest-centre-elevation-complete-starlink-at-geometric-horizon-v1",
        "minimum_elevation_deg": 0.0,
        "tie_break": "lowest-catalog-number",
        "response_accessed": False,
        "candidate_population_for_scoring": "complete-response-free-starlink-horizon-union-v1",
        "candidate_truncation_permitted": False,
    }:
        raise ValueError("response-free candidate selection policy differs from v1")

    pair_rows = _sequence(root["pairs"], "pairs")
    if len(pair_rows) != 3:
        raise ValueError("v1 requires exactly three paired hard-null backgrounds")
    backgrounds = {item.session_id: item for item in base_protocol.backgrounds}
    if len(backgrounds) != 3:
        raise ValueError("base protocol no longer contains exactly three backgrounds")
    pairs = tuple(_load_pair(item, backgrounds) for item in pair_rows)
    if tuple(item.background_session_id for item in pairs) != tuple(backgrounds):
        raise ValueError("paired backgrounds must preserve the frozen base order")
    for inventory, label in (
        ((item.pair_id for item in pairs), "pair"),
        ((item.orbit_scenario_id for item in pairs), "orbit scenario"),
        ((item.radio_scenario_id for item in pairs), "radio scenario"),
        ((item.seed for item in pairs), "seed"),
    ):
        values = tuple(inventory)
        if len(set(values)) != len(values):
            raise ValueError(f"{label} inventory must be unique")

    scoring = _mapping(root["scoring"], "scoring")
    _exact_keys(
        scoring,
        {
            "training_fraction",
            "future_fraction",
            "training_response",
            "future_response",
            "identical_supported_rows_across_model_families",
            "selection_and_nuisance_fit_use_future_response",
            "independent_unit",
            "independent_paired_background_count",
            "formal_95_percent_rank_minimum_paired_background_count",
            "formal_coverage_claimed",
            "threshold_fitting_permitted",
        },
        "scoring",
    )
    if scoring != {
        "training_fraction": 0.6,
        "future_fraction": 0.4,
        "training_response": "even-qin-cfo",
        "future_response": "odd-qin-cfo",
        "identical_supported_rows_across_model_families": True,
        "selection_and_nuisance_fit_use_future_response": False,
        "independent_unit": "background-pair",
        "independent_paired_background_count": 3,
        "formal_95_percent_rank_minimum_paired_background_count": 19,
        "formal_coverage_claimed": False,
        "threshold_fitting_permitted": False,
    }:
        raise ValueError("paired scoring policy differs from v1")
    _validate_claim_boundaries(root)
    return CrossFamilyInjectionProtocol(
        protocol_digest=protocol_digest,
        dataset_policy_path=dataset_policy_path,
        dataset_policy_sha256=dataset_policy_sha256,
        base_protocol_path=base_protocol_path,
        base_protocol_sha256=base_protocol_sha256,
        base_protocol=base_protocol,
        observer_site=observer_site,
        nominal_rf_hz=nominal_rf_hz,
        snr_db=snr_db,
        frame_occupancy=frame_occupancy,
        interpolation_spacing_s=interpolation_spacing_s,
        interpolation_maximum_error_hz=interpolation_maximum_error_hz,
        pairs=pairs,
        training_fraction=0.6,
        future_fraction=0.4,
    )


def _load_pair(value: object, backgrounds: Mapping[str, BackgroundSpan]) -> CrossFamilyTruthPair:
    row = _mapping(value, "pair")
    _exact_keys(row, _PAIR_KEYS, "pair")
    session_id = _string(row["background_session_id"], "background session")
    if session_id not in backgrounds:
        raise ValueError("paired background is absent from the frozen base protocol")
    background = backgrounds[session_id]
    sample_zero_utc_ns = _positive_int(row["sample_zero_utc_ns"], "sample-zero UTC")
    span_start_utc_ns = _positive_int(row["span_start_utc_ns"], "span-start UTC")
    span_centre_utc_ns = _positive_int(row["span_centre_utc_ns"], "span-centre UTC")
    nanoseconds_per_sample = 1_000_000_000 // background.sample_rate_hz
    if nanoseconds_per_sample * background.sample_rate_hz != 1_000_000_000:
        raise ValueError("sample rate must resolve exactly in UTC ns")
    if span_start_utc_ns != sample_zero_utc_ns + background.sample_start * nanoseconds_per_sample:
        raise ValueError("paired UTC span does not match the frozen sample coordinates")
    if (
        span_centre_utc_ns
        != span_start_utc_ns + background.sample_count * nanoseconds_per_sample // 2
    ):
        raise ValueError("paired centre does not bisect the frozen background span")
    collected = _positive_int(row["tle_collected_utc_ns"], "TLE collection UTC")
    if collected >= span_start_utc_ns:
        raise ValueError("TLE snapshot must be causal for the injected span")
    snapshot_digest = _digest(row["tle_snapshot_sha256"], "TLE snapshot digest")
    snapshot_path = Path(_string(row["tle_snapshot_path"], "TLE snapshot path"))
    if snapshot_path.name != snapshot_digest.removeprefix("sha256:") + ".tle":
        raise ValueError("TLE path name must identify the frozen snapshot digest")
    name = _string(row["true_object_name"], "true object name")
    if not name.startswith("STARLINK-"):
        raise ValueError("known orbit truth must be a named Starlink object")
    elevation = _finite_float(row["centre_elevation_deg"], "centre elevation")
    if not 0.0 <= elevation <= 90.0:
        raise ValueError("selected truth object must be above the geometric horizon")
    return CrossFamilyTruthPair(
        pair_id=_string(row["pair_id"], "pair identity"),
        background_session_id=session_id,
        sample_zero_utc_ns=sample_zero_utc_ns,
        span_start_utc_ns=span_start_utc_ns,
        span_centre_utc_ns=span_centre_utc_ns,
        seed=_nonnegative_int(row["seed"], "seed"),
        orbit_scenario_id=_string(row["orbit_scenario_id"], "orbit scenario"),
        radio_scenario_id=_string(row["radio_scenario_id"], "radio scenario"),
        tle_snapshot_path=snapshot_path,
        tle_snapshot_sha256=snapshot_digest,
        tle_collected_utc_ns=collected,
        tle_object_count=_positive_int(row["tle_object_count"], "TLE object count"),
        true_catalog_number=_positive_int(row["true_catalog_number"], "true catalog number"),
        true_object_name=name,
        true_element_digest=_digest(row["true_element_digest"], "true element digest"),
        true_element_epoch_utc_ns=_positive_int(
            row["true_element_epoch_utc_ns"], "true element epoch"
        ),
        centre_elevation_deg=elevation,
    )


def _validate_claim_boundaries(root: Mapping[str, Any]) -> None:
    limits = _mapping(root["interpretation_limits"], "interpretation_limits")
    expected_limits = {
        "development_only": True,
        "mechanistic_descriptive_only": True,
        "secure_norad_permitted": False,
        "positioning_validation_permitted": False,
        "posterior_odds_permitted": False,
        "model_selection_gate_permitted": False,
        "backgrounds_are_independent_count_of_six": False,
        "new_rf_collection_authorized": False,
    }
    _exact_keys(limits, set(expected_limits), "interpretation_limits")
    if limits != expected_limits:
        raise ValueError("cross-family claim boundary differs from v1")
    execution = _mapping(root["execution"], "execution")
    expected_execution = {
        "status": "frozen-not-executed",
        "iq_accessed_during_protocol_freeze": False,
        "tle_propagation_used_only_for-response-free-selection": True,
        "background_response_scored_during_protocol_freeze": False,
        "execution_authorized_by_this_document": False,
    }
    _exact_keys(execution, set(expected_execution), "execution")
    if execution != expected_execution:
        raise ValueError("cross-family execution boundary differs from v1")


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return dict(value)


def _sequence(value: object, label: str) -> tuple[object, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    return tuple(value)


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} keys differ from v1")


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _digest(value: object, label: str) -> str:
    text = _string(value, label)
    if _SHA256_RE.fullmatch(text) is None:
        raise ValueError(f"{label} must be a tagged SHA-256 digest")
    return text


def _finite_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    output = float(value)
    if not math.isfinite(output):
        raise ValueError(f"{label} must be finite")
    return output


def _positive_float(value: object, label: str) -> float:
    output = _finite_float(value, label)
    if output <= 0.0:
        raise ValueError(f"{label} must be positive")
    return output


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _repository_path(value: object, repository_root: Path, label: str) -> Path:
    relative = Path(_string(value, label))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{label} must be a repository-relative path")
    path = (repository_root / relative).resolve()
    try:
        path.relative_to(repository_root.resolve())
    except ValueError as error:
        raise ValueError(f"{label} escapes the repository") from error
    return path


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
