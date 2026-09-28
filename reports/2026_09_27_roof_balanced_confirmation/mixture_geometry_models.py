"""Export accepted calibration-only mixture models for geometry scoring."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import mixture_calibration_inputs as adapter
import run_mixture_calibration as calibration_runner
import run_mixture_polished_loso as polished_runner
import model_eval


HERE = Path(__file__).resolve().parent
ARMS = ("mean", "mixture")


@dataclass(frozen=True)
class GeometryCalibration:
    arm: str
    detection: model_eval.FittedModel
    ratio: model_eval.FittedModel
    ratio_variance: float


@dataclass(frozen=True)
class GeometryBundle:
    models: Mapping[str, GeometryCalibration]
    calibration_sha256: str
    calibration_sessions: tuple[str, ...]
    source_hashes: Mapping[str, str]
    artifact_sha256: Mapping[str, str]


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _expected_names(schema: dict, outcome: str) -> tuple[str, ...]:
    nuisance = tuple(schema[f"{outcome}_nuisance_names"])
    return nuisance + (("signed_east",) if outcome == "detection" else ("east",))


def _model(schema: dict, arm_payload: dict, outcome: str) -> model_eval.FittedModel:
    continuous = outcome == "ratio"
    expected = _expected_names(schema, outcome)
    actual = tuple(arm_payload["feature_names"][outcome])
    coefficients = tuple(float(value) for value in arm_payload["coefficients"][outcome])
    if actual != expected or len(coefficients) != len(expected):
        raise ValueError(f"{outcome} feature/coefficient shape mismatch")
    channel_edges = tuple(schema[f"{outcome}_channel_edges"])
    rates = tuple(schema[f"{outcome}_sample_rates"])
    if not channel_edges or not rates:
        raise ValueError("empty categorical feature levels")
    channels = tuple(sorted({value.split(":", 1)[0] for value in channel_edges}))
    edges = tuple(sorted({value.split(":", 1)[1] for value in channel_edges}))
    if continuous:
        numeric_names = ("east",)
        means = (float(schema["ratio_east_mean"]),)
        scales = (float(schema["ratio_east_scale"]),)
    else:
        numeric_names = ("log_anchor_margin", "signed_east")
        means = (float(schema["log_margin_mean"]),
                 float(schema["detection_east_mean"]))
        scales = (float(schema["log_margin_scale"]),
                  float(schema["detection_east_scale"]))
    if (not all(math.isfinite(value) for value in (*coefficients, *means, *scales)) or
            any(value <= 0 for value in scales)):
        raise ValueError("nonfinite coefficients or invalid scalers")
    return model_eval.FittedModel(
        outcome="continuous" if continuous else "detection", direction=True,
        feature_names=expected, channel_levels=channels, edge_levels=edges,
        channel_edge_levels=channel_edges, sample_rate_levels=rates,
        numeric_names=numeric_names, means=means, scales=scales,
        coefficients=coefficients)


def export_models(payload: dict) -> Mapping[str, GeometryCalibration]:
    if (not payload.get("calibration_accepted") or
            not payload.get("full_six_all_models_converged") or
            not payload.get("advancement_gate", {}).get("advance") or
            not all(payload["advancement_gate"].get("checks", {}).values()) or
            payload["advancement_gate"].get("failed_checks") != []):
        raise ValueError("mixture calibration acceptance gates did not pass")
    full = payload.get("descriptive_full_six", {})
    if (full.get("kind") != "descriptive_full_six_numerically_polished" or
            not full.get("all_models_converged")):
        raise ValueError("accepted full-six polished model is missing")
    schema = full.get("feature_schema", {})
    output = {}
    for arm in ARMS:
        source = full.get("models", {}).get(arm, {})
        if (source.get("arm") != arm or not source.get("converged") or
                not source.get("polish", {}).get("accepted")):
            raise ValueError(f"{arm} full-six model was not accepted")
        detection = _model(schema, source, "detection")
        ratio = _model(schema, source, "ratio")
        variance = float(source.get("variance"))
        log_sigma = float(source.get("log_sigma"))
        if (not math.isfinite(variance) or variance <= 0 or
                not math.isclose(variance, math.exp(2 * log_sigma), rel_tol=1e-12)):
            raise ValueError(f"{arm} ratio variance is invalid")
        output[arm] = GeometryCalibration(arm, detection, ratio, variance)
    return MappingProxyType(output)


def load_geometry_bundle() -> GeometryBundle:
    path = HERE / "mixture_calibration_polished.json"
    payload_bytes = path.read_bytes()
    payload = json.loads(payload_bytes)
    tracks, receipt = adapter.load_joined()
    expected_bindings = calibration_runner.source_bindings(receipt)
    expected_bindings["structural_input_sha256"] = adapter.structural_signature(tracks)
    if (payload.get("rows") != receipt["rows"] or
            payload.get("tracks") != receipt["tracks"] or
            payload.get("calibration_sessions") != receipt["sessions"] or
            payload.get("ridge") != calibration_runner.RIDGE or
            payload.get("bindings") != expected_bindings or
            payload.get("source_hashes") != polished_runner.source_hashes()):
        raise ValueError("mixture calibration input/code binding changed")
    recomputed_gate = polished_runner.mixture_advancement.evaluate_gate(
        payload.get("conditional_loso", []), receipt["sessions"])
    if payload.get("advancement_gate") != recomputed_gate:
        raise ValueError("mixture calibration advancement gate no longer reproduces")
    artifact_hashes = payload.get("artifact_sha256", {})
    expected_names = {"mixture-calibration-polished-full.json"} | {
        polished_runner.polished_fold_path(sid).name for sid in receipt["sessions"]}
    if set(artifact_hashes) != expected_names:
        raise ValueError("mixture calibration artifact inventory changed")
    for name, expected in artifact_hashes.items():
        if digest((HERE / name).read_bytes()) != expected:
            raise ValueError("mixture calibration artifact digest changed: " + name)
    full, full_sha = polished_runner.verified_polished_full(
        receipt["sessions"], expected_bindings)
    if digest((HERE / "mixture-calibration-polished-full.json").read_bytes()) != full_sha:
        raise ValueError("polished full-six digest changed")
    if payload.get("descriptive_full_six") != full:
        raise ValueError("embedded polished full-six model changed")
    models = export_models(payload)
    return GeometryBundle(
        models=models, calibration_sha256=digest(payload_bytes),
        calibration_sessions=tuple(receipt["sessions"]),
        source_hashes=MappingProxyType(dict(payload["source_hashes"])),
        artifact_sha256=MappingProxyType(dict(artifact_hashes)))


def load_geometry_models() -> Mapping[str, GeometryCalibration]:
    return load_geometry_bundle().models
