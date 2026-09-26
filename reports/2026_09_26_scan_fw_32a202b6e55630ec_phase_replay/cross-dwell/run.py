#!/usr/bin/env python3
"""Counter-anchored cross-dwell phase transport for the sealed boundary ledger."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import zstandard as zstd

RATE = 10_000_000
WINDOW = 16_384
STRIDE = 8_192
SESSION_ORIGIN = 492_145_132_025
SYMBOL_RATE = 250_000_000 / 1100


def wrap(x):
    return (np.asarray(x) + np.pi) % (2 * np.pi) - np.pi


def load(root, manifest, visit):
    c = manifest["chunks"][visit]
    raw = zstd.ZstdDecompressor().decompress(
        (root / c["relative_path"]).read_bytes(), max_output_size=c["uncompressed_bytes"]
    )
    if "sha256:" + hashlib.sha256(raw).hexdigest() != c["uncompressed_sha256"]:
        raise ValueError(f"digest {visit}")
    return np.frombuffer(raw, dtype="<i2").reshape(-1, 2, 2)


def series(a, b, c0, c1, origin):
    out = []
    taper = np.hanning(WINDOW) ** 2
    for iq, counter in ((a, c0), (b, c1)):
        x = iq[..., 0].astype(float) + 1j * iq[..., 1].astype(float)
        shift = series.receiver_time_shift_samples
        for s in range(0, len(x) - WINDOW - shift + 1, STRIDE):
            n = np.arange(s, s + WINDOW)
            t = (counter - origin + n) / RATE
            # The seed is applied per sample before the window average.
            seed = series.seed
            right = x[s + shift : s + shift + WINDOW, 1] * np.exp(-2j * np.pi * seed * t)
            p = np.sum(np.conj(x[s : s + WINDOW, 0]) * right * taper)
            den = math.sqrt(
                float(
                    np.sum(abs(x[s : s + WINDOW, 0]) ** 2 * taper) * np.sum(abs(right) ** 2 * taper)
                )
            )
            out.append(
                (
                    float((counter - origin + s + (WINDOW - 1) / 2) / RATE),
                    p,
                    counter,
                    float(abs(p) / max(den, 1e-30)),
                )
            )
    return out


series.seed = 0.0
series.receiver_time_shift_samples = 0


def fit(rows, left_counter):
    t = np.array([x[0] for x in rows])
    p = np.array([x[1] for x in rows])
    labels = np.array([x[2] for x in rows])
    coherence = np.array([x[3] for x in rows])
    dt = np.diff(t)
    mid = (t[1:] + t[:-1]) / 2
    dp = np.angle(p[1:] * np.conj(p[:-1]))
    same = labels[1:] == labels[:-1]
    boundary = int(np.flatnonzero(~same)[0])
    freq = dp / (2 * np.pi * dt)
    center = float(np.mean(mid))
    X = np.column_stack([np.ones(len(mid)), mid - center, (mid - center) ** 2])
    w = np.sqrt(abs(p[1:] * p[:-1]))

    def solve(mask):
        return np.linalg.lstsq(X[mask] * w[mask, None], freq[mask] * w[mask], rcond=None)[0]

    def pred(coef):
        def integ(x):
            y = x - center
            return coef[0] * y + coef[1] * y * y / 2 + coef[2] * y * y * y / 3

        return float(
            np.degrees(
                wrap(dp[boundary] - 2 * np.pi * (integ(t[boundary + 1]) - integ(t[boundary])))
            )
        )

    joint = solve(same)
    # With 50% overlap, exclude both increments whose raw union touches/overlaps
    # the held final-left endpoint window.
    causal = same & (np.arange(len(mid)) < boundary - 2)
    strict_joint = same & (
        (np.arange(len(mid)) < boundary - 2) | (np.arange(len(mid)) > boundary + 2)
    )
    causal_coef = solve(causal)
    causal_error = wrap(2 * np.pi * (freq[causal] - X[causal] @ causal_coef) * dt[causal])
    return {
        "joint_boundary_residual_deg": pred(joint),
        "strict_joint_boundary_residual_deg": pred(solve(strict_joint)),
        "causal_left_boundary_residual_deg": pred(causal_coef),
        "causal_training_rms_deg": float(np.degrees(np.sqrt(np.mean(causal_error**2)))),
        "boundary_dt_us": float(dt[boundary] * 1e6),
        "left_training_increment_count": int(causal.sum()),
        "joint_training_increment_count": int(same.sum()),
        "strict_joint_training_increment_count": int(strict_joint.sum()),
        "seed_only_boundary_deg": float(np.degrees(dp[boundary])),
        "minimum_boundary_endpoint_coherence": float(
            min(coherence[boundary], coherence[boundary + 1])
        ),
        "median_window_coherence": float(np.median(coherence)),
    }


def main(inp, out, root):
    out.parent.mkdir(parents=True, exist_ok=True)
    env = json.loads((root / "manifest.json").read_text())
    manifest = env["manifest"]
    rows = list(csv.DictReader(inp.open()))
    output = []
    for i, r in enumerate(rows):
        base = {
            "schema": "scan-cross-dwell/v1",
            "left_visit": int(r["left_visit"]),
            "right_visit": int(r["right_visit"]),
            "split": r["split"],
            "channel": int(r["channel"]),
            "overlapping_edge_group": int(r["overlapping_edge_group"]),
        }
        if r["all_four_sparse_acquisitions_pass"] != "True":
            output.append(
                {**base, "status": "rejected", "reason": "not_all_four_sparse_acquisitions_pass"}
            )
            continue
        l0, l1, r0, r1 = (
            float(r[k])
            for k in (
                "left_rx0_absolute_cfo_hz",
                "left_rx1_absolute_cfo_hz",
                "right_rx0_absolute_cfo_hz",
                "right_rx1_absolute_cfo_hz",
            )
        )
        left_seed = l1 - l0
        joint_seed = ((l1 - l0) + (r1 - r0)) / 2
        if max(abs(r0 - l0), abs(r1 - l1), abs((r1 - r0) - (l1 - l0))) > SYMBOL_RATE / 2:
            output.append(
                {
                    **base,
                    "status": "rejected",
                    "reason": "phase_blind_cfo_association_exceeds_half_symbol",
                }
            )
            continue
        a = load(root, manifest, base["left_visit"])
        b = load(root, manifest, base["right_visit"])
        series.seed = joint_seed
        series.receiver_time_shift_samples = 0
        joint = fit(
            series(
                a, b, int(r["left_start_counter"]), int(r["right_start_counter"]), SESSION_ORIGIN
            ),
            SESSION_ORIGIN,
        )
        aliases = []
        for alias in (-1, 0, 1):
            series.seed = left_seed + alias * SYMBOL_RATE
            candidate = fit(
                series(
                    a,
                    b,
                    int(r["left_start_counter"]),
                    int(r["right_start_counter"]),
                    SESSION_ORIGIN,
                ),
                SESSION_ORIGIN,
            )
            aliases.append((candidate["causal_training_rms_deg"], alias, candidate))
        _, chosen_alias, causal = min(aliases, key=lambda x: x[0])
        wrong = min((x for x in aliases if x[1] != chosen_alias), key=lambda x: x[0])[2]
        series.seed = left_seed + chosen_alias * SYMBOL_RATE
        series.receiver_time_shift_samples = 4093
        wrong_time = fit(
            series(
                a, b, int(r["left_start_counter"]), int(r["right_start_counter"]), SESSION_ORIGIN
            ),
            SESSION_ORIGIN,
        )
        series.receiver_time_shift_samples = 0
        result = {
            **joint,
            "causal_left_boundary_residual_deg": causal["causal_left_boundary_residual_deg"],
            "left_training_increment_count": causal["left_training_increment_count"],
        }
        output.append(
            {
                **base,
                "status": "complete",
                "joint_relative_cfo_seed_hz": joint_seed,
                "causal_left_relative_cfo_seed_hz": left_seed + chosen_alias * SYMBOL_RATE,
                "train_selected_symbol_alias": chosen_alias,
                "causal_training_rms_deg": causal["causal_training_rms_deg"],
                "wrong_alias_boundary_residual_deg": wrong["causal_left_boundary_residual_deg"],
                "wrong_receiver_time_shift_samples": 4093,
                "wrong_receiver_time_boundary_residual_deg": wrong_time[
                    "causal_left_boundary_residual_deg"
                ],
                "session_counter_origin": SESSION_ORIGIN,
                "window_samples": WINDOW,
                "historical_joint_diagnostic": True,
                "absolute_phase_resolved": False,
                **result,
            }
        )
        if i % 20 == 0:
            print(i, flush=True)
    out.write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in output))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("root", type=Path)
    a = p.parse_args()
    main(a.input, a.output, a.root)
