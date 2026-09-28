#!/usr/bin/env python3
"""Exact DS7 baseline with batched stationary-offset fixed-point iterations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

import ds7_baseline_adapter as baseline

REFERENCE_RF_HZ = baseline.REFERENCE_RF_HZ
Stationary = baseline.Stationary
JointObjective = baseline.JointObjective
load_documents = baseline.load_documents


def fit_stationary_offsets(values: np.ndarray, sigma: float = 100.0):
    """Reproduce the frozen scalar profiler while batching its dominant loop."""
    values = np.asarray(values, dtype=float)
    centers = np.median(values, axis=1)
    ys = values - centers[:, None]
    starts = [np.unique(np.r_[np.quantile(y, np.linspace(0, 1, 9)), 0.0]) for y in ys]

    # Duplicate quantiles are unusual, but grouping by start count preserves the
    # scalar algorithm for them without padding or adding synthetic starts.
    guesses = [None] * len(ys)
    for width in sorted({len(row) for row in starts}):
        indices = [index for index, row in enumerate(starts) if len(row) == width]
        group_y = ys[indices]
        group_guesses = np.stack([starts[index] for index in indices])
        active = np.ones(group_guesses.shape, dtype=bool)
        for _ in range(100):
            r = (group_y[:, None, :] - group_guesses[:, :, None]) / sigma
            weights = 5 / (4 + r * r)
            new = (
                (weights * group_y[:, None, :]).sum(axis=2)
                - sigma * sigma * centers[indices, None] / 1e12
            ) / (weights.sum(axis=2) + sigma * sigma / 1e12)
            done = np.abs(new - group_guesses) < 1e-6
            group_guesses = np.where(active, new, group_guesses)
            active &= ~done
            if not active.any():
                break
        for local, index in enumerate(indices):
            guesses[index] = group_guesses[local]

    offsets, audits = [], []
    distances = np.array([1e-4, 0.01, 1.0, 10.0, 100.0, 1000.0])
    for center, y, row_starts, row_guesses in zip(
        centers, ys, starts, guesses, strict=True
    ):
        lower, upper = min(float(y.min()), -center), max(float(y.max()), -center)
        if lower == upper:
            offsets.append(center + lower)
            audits.append({"converged": True, "gradient": 0.0, "roots": 1})
            continue

        def loss(v):
            return float(
                2.5 * np.log1p(((y - v) / sigma) ** 2 / 4).sum()
                + 0.5 * ((center + v) / 1e6) ** 2
            )

        def derivative(v):
            r = v - y
            return float(np.sum(5 * r / (4 * sigma * sigma + r * r)) + (center + v) / 1e12)

        def curvature(v):
            r = v - y
            den = 4 * sigma * sigma + r * r
            return float(np.sum(5 * (4 * sigma * sigma - r * r) / den**2) + 1e-12)

        nodes = np.unique(
            np.r_[
                lower,
                upper,
                row_starts,
                row_guesses,
                np.clip(row_guesses[:, None] - distances, lower, upper).ravel(),
                np.clip(row_guesses[:, None] + distances, lower, upper).ravel(),
            ]
        )
        residual = nodes[:, None] - y[None, :]
        gradients = (
            np.sum(5 * residual / (4 * sigma * sigma + residual * residual), axis=1)
            + (center + nodes) / 1e12
        )
        roots = []
        for index in range(len(nodes) - 1):
            if gradients[index] <= 0 <= gradients[index + 1]:
                root = brentq(
                    derivative, nodes[index], nodes[index + 1], xtol=1e-9, rtol=1e-14
                )
                if curvature(root) > 0:
                    roots.append(root)
        if not roots:
            raise RuntimeError("no positive-curvature stationary offset")
        best = min(roots, key=loss)
        gradient = derivative(best)
        offsets.append(center + best)
        audits.append(
            {"converged": abs(gradient) < 1e-7, "gradient": gradient, "roots": len(roots)}
        )
    return np.asarray(offsets), audits


def profile(residual: np.ndarray, mask: np.ndarray):
    offsets, audits = fit_stationary_offsets(residual[:, mask])
    z = (residual - offsets[:, None]) / 100.0
    density = (
        baseline.gammaln(2.5)
        - baseline.gammaln(2)
        - 0.5 * np.log(4 * np.pi)
        - np.log(100.0)
        - 2.5 * np.log1p(z * z / 4)
    )
    train = density[:, mask].sum(axis=1) - 0.5 * offsets**2 / 1e12
    joint = density.sum(axis=1) - 0.5 * offsets**2 / 1e12
    return train, joint, audits, offsets


def training_rms_hz(documents: list[dict], config: dict, x: np.ndarray) -> float:
    """Pooled training RMS at each track's visible MAP catalogue candidate."""
    squared_error = 0.0
    count = 0
    models = [baseline.Stationary(document, config) for document in documents]
    for document_index, model in enumerate(models):
        local = np.array([x[0], x[1], x[document_index + 2]])
        for track in model.document["tracks"]:
            prediction, visible = model.prediction(track, local)
            residual = track["y"][None, :] - prediction
            score, _, audits, offsets = profile(residual, track["mask"])
            if not all(audit["converged"] for audit in audits):
                raise RuntimeError("offset stationarity check failed")
            score = np.where(visible, score, -np.inf)
            if not np.isfinite(score).any():
                raise RuntimeError("no visible training candidate")
            winner = int(np.argmax(score))
            centered = residual[winner, track["mask"]] - offsets[winner]
            squared_error += float(centered @ centered)
            count += len(centered)
    if count == 0:
        raise RuntimeError("no training observations")
    return float(np.sqrt(squared_error / count))


def estimate(request: dict) -> dict:
    # Stationary.evaluate resolves this module global in the frozen implementation.
    # Installing the equivalent batched profiler leaves all geometry and solver
    # behavior in the reviewed baseline implementation.
    original = baseline.profile
    baseline.profile = profile
    try:
        result = baseline.estimate(request)
    finally:
        baseline.profile = original
    if result.get("status") == "ok":
        documents = load_documents(request)
        diagnostics = result["diagnostics"]
        x = np.asarray(
            diagnostics["east_north_km"] + diagnostics["timing_offsets_s"], dtype=float
        )
        rms = training_rms_hz(documents, request["config"], x)
        result["rf_rms_hz"] = rms
        diagnostics["rf_rms_hz"] = rms
        diagnostics["rf_rms_definition"] = (
            "pooled training-observation residual RMS using each track's training-MAP "
            "visible candidate and stationary training offset"
        )
        diagnostics["rf_rms_limitation"] = (
            "training conditional metric; catalogue ambiguity is not resolved by held-out "
            "or reference information"
        )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()
    result = estimate(json.loads(args.request.read_text()))
    with args.response.open("x") as stream:
        json.dump(result, stream, allow_nan=False)


if __name__ == "__main__":
    main()
