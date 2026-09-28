"""Local, conditional receiver-drift screen over frozen DS7 numerical inputs.

This is not a calibrated clock fit or a full mixture-likelihood Hessian.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

from tools import ds7_baseline_adapter as baseline
from tools.ds7_clock_gate import identifiability, recover_injected_bias
from tools.ds7_eval import file_digest, seal_object, write_json


def drift_column(times, receiver, target, rf_hz, *, physical_baseband=False):
    times = np.asarray(times, dtype=float)
    if receiver != target:
        return np.zeros_like(times)
    scale = baseline.REFERENCE_RF_HZ / rf_hz if physical_baseband else 1.0
    return (times - times.mean()) * scale


def local_design(document, config, point):
    model = baseline.Stationary(document, config)
    tracks = document["tracks"]
    receivers = sorted({t["receiver_id"] for t in tracks})
    blocks, clocks = [], {policy: [] for policy in ("canonical", "physical_baseband")}
    posterior_maxima = []
    for index, track in enumerate(tracks):
        mask = track["mask"]
        prediction, visible = model.prediction(track, point)
        residual = track["y"][None, :] - prediction
        scores, _, audits, offsets = baseline.profile(residual, mask)
        if not all(a["converged"] for a in audits):
            raise ValueError("offset stationarity failed")
        scores = np.where(visible, scores, -np.inf)
        normal = logsumexp(scores)
        if not np.isfinite(normal):
            raise ValueError("no visible finite candidate")
        probabilities = np.exp(scores - normal)
        posterior_maxima.append(float(probabilities.max()))
        centered = residual[:, mask] - offsets[:, None]
        # Positive IRLS weights are a local sensitivity screen, not observed
        # information: responsibilities and weights are frozen at this point.
        weights = np.sqrt(probabilities @ (5 / (40000 + centered**2)))
        block = np.zeros((mask.sum(), len(tracks) + 3))
        block[:, index] = 1.0
        for axis, step in enumerate((1e-4, 1e-4, 1e-5)):
            plus, minus = point.copy(), point.copy()
            plus[axis] += step
            minus[axis] -= step
            if axis == 2:
                plus[axis], minus[axis] = min(5.0, plus[axis]), max(-5.0, minus[axis])
            derivative = (model.prediction(track, plus)[0] - model.prediction(track, minus)[0]) / (
                plus[axis] - minus[axis]
            )
            block[:, len(tracks) + axis] = probabilities @ derivative[:, mask]
        blocks.append(block * weights[:, None])
        times = np.asarray(track["times_s"])[mask]
        for policy in clocks:
            columns = np.column_stack(
                [
                    drift_column(
                        times,
                        track["receiver_id"],
                        receiver,
                        track["rf_hz"],
                        physical_baseband=policy == "physical_baseband",
                    )
                    for receiver in receivers
                ]
            )
            clocks[policy].append(columns * weights[:, None])
    return (
        np.vstack(blocks),
        {p: np.vstack(c) for p, c in clocks.items()},
        receivers,
        posterior_maxima,
    )


def audit(request, response):
    if response.get("status") != "ok" or not response["converged"] or response["boundary_hit"]:
        raise ValueError("screen requires an interior converged baseline")
    documents = baseline.load_documents(request)
    diagnostics = response["diagnostics"]
    rows = []
    for number, document in enumerate(documents):
        point = np.array([*diagnostics["east_north_km"], diagnostics["timing_offsets_s"][number]])
        base, clocks, receivers, probabilities = local_design(document, request["config"], point)
        for policy, columns in clocks.items():
            for index, receiver in enumerate(receivers):
                # Test each receiver jointly with all other receiver drifts.
                nuisance = np.column_stack((base, np.delete(columns, index, axis=1)))
                result = asdict(identifiability(nuisance, columns[:, index]))
                if not np.isfinite(result["scaled_condition_number"]):
                    result["scaled_condition_number"] = None
                result.update(
                    session_id=document["session_id"],
                    receiver_id=receiver,
                    units_policy=policy,
                    training_observations=len(base),
                    synthetic_linear_recovery=[
                        recover_injected_bias(nuisance, columns[:, index], value)
                        for value in (-1.0, 0.0, 1.0)
                    ],
                    minimum_track_max_posterior=min(probabilities),
                )
                rows.append(result)
    return {
        "schema": "ds7-conditional-clock-jacobian/v1",
        "rows": rows,
        "gate": "hold_no_independent_calibration",
        "clock_fit_attempted": False,
        "reference_access": "none; baseline prediction used as local linearization point",
        "method": (
            "Training-only posterior-mean prediction derivatives; fixed responsibilities and "
            "positive Student-t IRLS weights; project against all track offsets, position, "
            "recording time and other receiver drift"
        ),
        "limitations": [
            "Local conditional sensitivity screen, not full mixture information or "
            "global identifiability",
            "Normalized-Hz drift and physical-baseband-Hz drift are distinct; physical "
            "drift is scaled by canonical RF / actual RF",
            "Synthetic +/-1 linear recovery is algebraic only; no physical drift bounds "
            "or nonlinear injection test established",
            "No sharing across captures and no independent calibration supplied",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--prediction", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(json.loads(args.request.read_text()), json.loads(args.prediction.read_text()))
    report["input_sha256"] = {str(p): file_digest(p) for p in (args.request, args.prediction)}
    report["code_sha256"] = {
        str(p): file_digest(p)
        for p in (
            Path(__file__),
            Path(baseline.__file__),
            Path("tools/ds7_clock_gate.py"),
        )
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, seal_object(report))


if __name__ == "__main__":
    main()
