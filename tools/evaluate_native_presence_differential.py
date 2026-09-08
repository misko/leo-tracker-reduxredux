#!/usr/bin/env python3
"""Explore differential pilot proposals on frozen probes without radio access."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

import numpy as np

from tools.native_presence import ROOT
from tools.qualify_native_presence import digest, write_json


def read_probe(path):
    data = path.read_bytes()
    magic, rate, edge, count, fmt, counter = struct.unpack_from("<4sIIIIQ", data)
    if magic != b"LPR1" or rate not in (2500000, 5000000) or edge > 1 or fmt not in (1, 2):
        raise ValueError("unsupported probe")
    n = round(rate / 750)
    size = 16 if fmt == 1 else 4
    if count != rate // 50 or len(data) != 28 + 32 * n + size * count:
        raise ValueError("invalid probe size")
    template = np.frombuffer(data, dtype="<c16", count=n, offset=28)
    if fmt == 1:
        samples = np.frombuffer(data, dtype="<c16", offset=28 + 32 * n)
    else:
        raw = np.frombuffer(data, dtype="<i2", offset=28 + 32 * n).reshape(-1, 2)
        samples = raw[:, 0].astype(float) + 1j * raw[:, 1]
    return samples, template, rate, edge, counter


def centered_projection(values, bins):
    values = values - values.mean()
    if bins:
        n = len(values)
        values = np.interp(np.arange(bins) * n / bins, np.arange(n), values, period=n)
        values -= values.mean()
    return values


def correlation(samples, template, rate, lag, bins=0):
    if lag < 0 or lag >= len(template):
        raise ValueError("invalid lag")
    n = len(template)
    products = (
        samples[lag:] * np.conj(samples[: len(samples) - lag]) if lag else np.abs(samples) ** 2
    )
    pilot = np.roll(template, -lag) * np.conj(template)
    folded, support = np.zeros(n, dtype=np.complex128), np.zeros(n)
    for frame in range(16):
        start = round(frame * rate / 750)
        valid = min(n, len(products) - start)
        if valid <= 0:
            break
        folded[:valid] += products[start : start + valid]
        support[:valid] += 1
    folded /= np.maximum(support, 1)
    folded, pilot = centered_projection(folded, bins), centered_projection(pilot, bins)
    norm = np.linalg.norm(folded) * np.linalg.norm(pilot)
    if not norm:
        return np.zeros(n, dtype=np.complex128)
    result = np.fft.ifft(np.fft.fft(folded) * np.conj(np.fft.fft(pilot))) / norm
    if bins:
        result = np.interp(np.arange(n) * bins / n, np.arange(bins), result, period=bins)
    return result


def select_peaks(values, lag, count, separation):
    scores = np.abs(values) if lag else values.real
    maxima = np.flatnonzero(
        (scores >= np.roll(scores, 1))
        & (scores >= np.roll(scores, -1))
        & ((scores > np.roll(scores, 1)) | (scores > np.roll(scores, -1)))
    )
    ordered = sorted(maxima, key=lambda k: (-scores[k], k))
    result = []
    for index in ordered:
        if scores[index] <= 0:
            break
        if any(min(abs(index - k), len(scores) - abs(index - k)) < separation for k in result):
            continue
        result.append(int(index))
        if len(result) == count:
            break
    return result


def evaluate(inputs_dir, output, protocol_path):
    output = output.resolve()
    if output.is_relative_to(Path("/mnt/qnap01")) or output.is_relative_to(Path("/srv/bulk/leo")):
        raise ValueError("non-archive output required")
    output.mkdir(parents=True, exist_ok=False)
    protocol = json.loads(protocol_path.read_text())
    inputs = json.loads((inputs_dir / "inputs.json").read_text())
    write_json(
        output / "protocol.json",
        {
            "protocol": protocol,
            "protocol_sha256": digest(protocol_path),
            "inputs_sha256": digest(inputs_dir / "inputs.json"),
            "source_sha256": digest(Path(__file__)),
        },
    )
    rows = []
    for probe in inputs:
        path = inputs_dir / probe["file"]
        if path.name != probe["file"] or digest(path) != probe["sha256"]:
            raise ValueError("probe identity changed")
        samples, template, rate, edge, counter = read_probe(path)
        if (
            rate != probe["rate_hz"]
            or edge != int(probe["edge"] == "upper")
            or str(counter) != probe["device_counter"]
        ):
            raise ValueError("probe header mismatch")
        references = [
            c for c in probe["oracle_candidates"] if c["margin"] >= protocol["reference_margin"]
        ]
        for lag in protocol["lags_samples"]:
            for bins in protocol["phase_bins"]:
                values = correlation(samples, template, rate, lag, bins)
                peaks = select_peaks(
                    values, lag, protocol["retained_peaks"], protocol["minimum_separation_samples"]
                )
                evidence = []
                for epoch in peaks:
                    phase_cfo = (
                        float(np.angle(values[epoch]) * rate / (2 * np.pi * lag)) if lag else None
                    )
                    matches = []
                    for ref in references:
                        difference = (
                            epoch - ref["epoch_sample"] - ref["fractional_offset_samples"]
                        ) % (rate / 750)
                        if (
                            min(difference, rate / 750 - difference)
                            <= protocol["timing_match_samples"]
                        ):
                            matches.append(
                                {
                                    "reference_cfo_hz": ref["tracking_cfo_hz"],
                                    "phase_cfo_error_hz": phase_cfo - ref["tracking_cfo_hz"]
                                    if lag
                                    else None,
                                }
                            )
                    evidence.append(
                        {
                            "epoch": epoch,
                            "score": float(abs(values[epoch]) if lag else values[epoch].real),
                            "phase_cfo_hz": phase_cfo,
                            "reference_timing_matches": matches,
                        }
                    )
                rows.append(
                    {
                        "probe": probe["file"],
                        "rate_hz": rate,
                        "edge": probe["edge"],
                        "lag": lag,
                        "bins": bins,
                        "provenance": probe["provenance"],
                        "reference_positive": bool(references),
                        "peaks": evidence,
                    }
                )
    write_json(output / "results.json", rows)
    for lag in protocol["lags_samples"]:
        for bins in protocol["phase_bins"]:
            for rate in (2500000, 5000000):
                selected = [
                    r
                    for r in rows
                    if r["lag"] == lag
                    and r["bins"] == bins
                    and r["rate_hz"] == rate
                    and "session_id" in r["provenance"]
                    and r["reference_positive"]
                ]
                print(
                    lag,
                    bins,
                    rate,
                    "positive",
                    len(selected),
                    "top1/top2/top8 timing matches",
                    [
                        sum(
                            any(p["reference_timing_matches"] for p in r["peaks"][:k])
                            for r in selected
                        )
                        for k in (1, 2, 8)
                    ],
                    flush=True,
                )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=ROOT / "config/analysis/arm-presence-differential-proposal-v1.json",
    )
    args = parser.parse_args()
    evaluate(args.inputs, args.output, args.protocol)


if __name__ == "__main__":
    main()
