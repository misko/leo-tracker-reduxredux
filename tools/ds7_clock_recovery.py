#!/usr/bin/env python3
"""Synthetic receiver-drift recovery through the frozen DS7 full mixture."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp


def _baseline_module():
    path = Path(__file__).with_name("ds7_baseline_adapter.py")
    spec = importlib.util.spec_from_file_location("ds7_clock_baseline", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load baseline numerical oracle")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def drift_column(track: dict) -> np.ndarray:
    """Normalized-Hz response to one native-Hz/s slope."""
    times = np.asarray(track["times_s"], dtype=float)
    return 11_200_000_000.0 / float(track["rf_hz"]) * (times - np.mean(times))


def profiled_single_loglike_gradient(
    y: np.ndarray, prediction: np.ndarray, mask: np.ndarray, column: np.ndarray, slope: float
) -> tuple[float, float]:
    """Small envelope-gradient oracle used by component tests."""
    baseline = _baseline_module()
    residual = y - prediction - slope * column
    offset, audit = baseline.fit_stationary_offset(residual[mask])
    if not audit["converged"]:
        raise RuntimeError("offset profile did not converge")
    centered = residual[mask] - offset
    value = float(np.sum(-2.5 * np.log1p((centered / 100.0) ** 2 / 4.0)) - 0.5 * offset**2 / 1e12)
    score = 5.0 * centered / (40_000.0 + centered**2)
    gradient = float(np.sum(score * column[mask]))
    return value, gradient


class DriftMixture:
    def __init__(self, document: dict, config: dict, baseline, deadline: float | None = None):
        self.document = document
        self.model = baseline.Stationary(document, config)
        self.profile = baseline.profile
        self.deadline = deadline

    def value_gradient(self, x: np.ndarray) -> tuple[float, np.ndarray]:
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise TimeoutError("case analyzer deadline exceeded")
        total = 0.0
        derivative = np.zeros(5, dtype=float)
        local = np.asarray(x[:3], dtype=float)
        for track in self.document["tracks"]:
            prediction, visible = self.model.prediction(track, local)
            column = drift_column(track)
            receiver = int(track["receiver_id"])
            prediction = prediction + x[3 + receiver] * column[None, :]
            residual = track["y"][None, :] - prediction
            score, _, audits, offsets = self.profile(residual, track["mask"])
            if not all(audit["converged"] for audit in audits):
                raise RuntimeError("offset stationarity check failed")
            score = np.where(visible, score, -np.inf)
            normal = logsumexp(score)
            total += float(normal - math.log(track["catalogue_size"]))
            responsibility = np.exp(score - normal)
            centered = residual[:, track["mask"]] - offsets[:, None]
            influence = 5.0 * centered / (40_000.0 + centered**2)
            for axis in range(3):
                step = 1e-4 if axis < 2 else 1e-5
                plus, minus = local.copy(), local.copy()
                plus[axis] += step
                minus[axis] -= step
                if axis == 2:
                    plus[axis], minus[axis] = min(5.0, plus[axis]), max(-5.0, minus[axis])
                delta = (
                    self.model.prediction(track, plus)[0] - self.model.prediction(track, minus)[0]
                ) / (plus[axis] - minus[axis])
                derivative[axis] += float(
                    responsibility @ np.sum(influence * delta[:, track["mask"]], axis=1)
                )
            derivative[3 + receiver] += float(
                responsibility @ np.sum(influence * column[track["mask"]][None, :], axis=1)
            )
        return -total, -derivative


def synthesize(
    document: dict, config: dict, truth: np.ndarray, slopes: tuple[float, float], baseline
):
    model = baseline.Stationary(document, config)
    generated = {**document, "tracks": []}
    selections = []
    for source in document["tracks"]:
        track = dict(source)
        prediction, visible = model.prediction(track, truth)
        residual = track["y"][None, :] - prediction
        score, _, audits, offsets = baseline.profile(residual, track["mask"])
        if not all(audit["converged"] for audit in audits):
            raise RuntimeError("donor offset profile did not converge")
        score = np.where(visible, score, -np.inf)
        selected = int(np.argmax(score))
        receiver = int(track["receiver_id"])
        track["y"] = (
            prediction[selected] + offsets[selected] + slopes[receiver] * drift_column(track)
        )
        generated["tracks"].append(track)
        selections.append(
            {
                "track_id": track["track_id"],
                "candidate_index": selected,
                "training_offset_hz": float(offsets[selected]),
            }
        )
    return generated, selections


def projected_rank(document: dict, config: dict, truth: np.ndarray, baseline) -> dict:
    model = baseline.Stationary(document, config)
    blocks = []
    for track in document["tracks"]:
        prediction, visible = model.prediction(track, truth)
        residual = track["y"][None, :] - prediction
        score = baseline.profile(residual, track["mask"])[0]
        selected = int(np.argmax(np.where(visible, score, -np.inf)))
        mask = track["mask"]
        columns = []
        for axis in range(3):
            step = 1e-4 if axis < 2 else 1e-5
            plus, minus = truth.copy(), truth.copy()
            plus[axis] += step
            minus[axis] -= step
            columns.append(
                (
                    model.prediction(track, plus)[0][selected]
                    - model.prediction(track, minus)[0][selected]
                )
                / (plus[axis] - minus[axis])
            )
        receiver_columns = np.zeros((len(track["y"]), 2))
        receiver_columns[:, int(track["receiver_id"])] = drift_column(track)
        design = np.column_stack((*columns, receiver_columns))[mask]
        design -= np.mean(design, axis=0, keepdims=True)
        blocks.append(design)
    matrix = np.vstack(blocks)
    singular = np.linalg.svd(matrix, compute_uv=False)
    tolerance = singular[0] * max(matrix.shape) * np.finfo(float).eps
    rank = int(np.sum(singular > tolerance))
    return {
        "rows": int(matrix.shape[0]),
        "columns": int(matrix.shape[1]),
        "rank": rank,
        "singular_values": singular.tolist(),
        "condition_number": float(singular[0] / singular[-1]),
    }


def run_case(document, config, spec, slopes, baseline) -> dict:
    started = time.monotonic()
    truth = np.asarray([*spec["donor_position_east_north_km"], spec["donor_tau_s"]], dtype=float)
    synthetic, selections = synthesize(document, config, truth, tuple(slopes), baseline)
    objective = DriftMixture(
        synthetic, config, baseline, deadline=started + spec["case_limit_seconds"]
    )
    bounds = [tuple(value) for value in spec["bounds"]]
    fits = []
    try:
        for start in spec["starts"]:
            fits.append(
                minimize(
                    objective.value_gradient,
                    np.asarray(start, dtype=float),
                    method="L-BFGS-B",
                    jac=True,
                    bounds=bounds,
                    options={
                        "maxiter": 100,
                        "maxfun": 180,
                        "ftol": 1e-10,
                        "gtol": 1e-5,
                        "maxls": 30,
                    },
                )
            )
    except TimeoutError:
        return {
            "injected_native_hz_s": slopes,
            "state": "timeout",
            "qualified": False,
            "elapsed_seconds": time.monotonic() - started,
            "training_map": selections,
        }
    fit = min(fits, key=lambda item: item.fun)
    elapsed = time.monotonic() - started
    position_error_m = float(np.linalg.norm(fit.x[:2] - truth[:2]) * 1000.0)
    tau_error_s = float(abs(fit.x[2] - truth[2]))
    slope_error = np.abs(fit.x[3:] - np.asarray(slopes))
    thresholds = spec["thresholds"]
    qualified = bool(
        fit.success
        and elapsed <= spec["case_limit_seconds"]
        and position_error_m <= thresholds["position_error_m"]
        and tau_error_s <= thresholds["tau_error_s"]
        and np.max(slope_error) <= thresholds["receiver_slope_error_hz_s"]
    )
    return {
        "injected_native_hz_s": slopes,
        "estimate": fit.x.tolist(),
        "position_error_m": position_error_m,
        "tau_error_s": tau_error_s,
        "receiver_slope_error_hz_s": slope_error.tolist(),
        "converged": bool(fit.success),
        "boundary_hit": any(
            abs(value - low) < 1e-3 or abs(value - high) < 1e-3
            for value, (low, high) in zip(fit.x, bounds, strict=True)
        ),
        "qualified": qualified,
        "elapsed_seconds": elapsed,
        "nfev_total": sum(int(item.nfev) for item in fits),
        "training_map": selections,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text())
    request = json.loads(args.request.read_text())
    baseline = _baseline_module()
    documents = baseline.load_documents(request)
    if len(documents) != 1:
        raise ValueError("clock recovery requires the first-single frozen bank")
    document = documents[0]
    truth = np.asarray([*spec["donor_position_east_north_km"], spec["donor_tau_s"]])
    rank = projected_rank(document, request["config"], truth, baseline)
    started = time.monotonic()
    cases = []
    for slopes in spec["cases_native_hz_s"]:
        case = run_case(document, request["config"], spec, slopes, baseline)
        cases.append(case)
        if case["elapsed_seconds"] > spec["case_limit_seconds"]:
            break
        if time.monotonic() - started > spec["total_limit_seconds"]:
            break
    result = {
        "schema": "ds7-clock-recovery-result/v1",
        "status": "qualified"
        if len(cases) == len(spec["cases_native_hz_s"])
        and all(c["qualified"] for c in cases)
        and rank["rank"] == 5
        else "unqualified",
        "projected_rank": rank,
        "cases": cases,
        "analyzer_seconds": time.monotonic() - started,
        "limitations": [
            "synthetic observations at a sealed non-reference donor estimate",
            "training-MAP candidate identities inherited from the baseline mixture",
            "no calibrated receiver-drift prior and no real clock or position claim",
        ],
        "reference_audit": "reference_excluded",
    }
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
