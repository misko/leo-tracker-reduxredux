#!/usr/bin/env python3
"""Evaluate stationary-tone nuisance fitting on saved development IQ and controls."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from leo.analysis.research.tone_nuisance import remove_stationary_tone
from tools.evaluate_native_presence_budgets import associated
from tools.evaluate_native_presence_differential import read_probe
from tools.native_presence import ROOT, NativePresence, build_library
from tools.qualify_native_presence import digest, write_json


def candidates(result):
    return [
        {
            key: getattr(c, key)
            for key in (
                "epoch",
                "fractional_complete",
                "fractional_offset_samples",
                "acquired_cfo_hz",
                "tracking_cfo_hz",
                "exact_score",
                "control_score",
                "margin",
            )
        }
        for c in result.candidates[: result.candidate_count]
    ]


def evaluate(inputs_dir, output):
    output = output.resolve()
    if output.is_relative_to(Path("/mnt/qnap01")) or output.is_relative_to(Path("/srv/bulk/leo")):
        raise ValueError("non-archive output required")
    output.mkdir(parents=True, exist_ok=False)
    policy_path = ROOT / "config/analysis/arm-presence-tone-nuisance-v1.json"
    policy = json.loads(policy_path.read_text())
    if (
        policy["three_bin_spectral_fraction_min"] != 0.02
        or policy["fit_power_fraction_min"] != 0.01
        or policy["refinement_lags"] != [256, 4096, 16384]
    ):
        raise ValueError("policy differs from the reviewed nuisance implementation")
    detector_path = ROOT / policy["detector_protocol"]
    detector = json.loads(detector_path.read_text())
    variant = detector["variants"][0]
    write_json(
        output / "protocol.json",
        {
            "policy": policy,
            "detector": detector,
            "inputs_sha256": digest(inputs_dir / "inputs.json"),
            "source_sha256": digest(Path(__file__)),
            "nuisance_source_sha256": digest(ROOT / "src/leo/analysis/research/tone_nuisance.py"),
        },
    )
    flags = tuple(detector["common_flags"]) + tuple(
        f"-DLEO_PRESENCE_{k}={v}" for k, v in variant["defines"].items()
    )
    library = build_library(output / "presence.so", cflags=flags)
    rows = []

    def run(values, rate, edge, provenance, reference):
        cleaned, fit = remove_stationary_tone(values, rate)
        with NativePresence(library, rate, edge) as native:
            raw, residual = candidates(native.run(values)), candidates(native.run(cleaned))

        def evidence(c):
            positive = [x for x in c if x["fractional_complete"] and x["margin"] >= 0.025]
            return {
                "detected": bool(positive),
                "reference_associated": any(
                    associated(a, r, rate, detector["reference_association"])
                    for a in positive
                    for r in reference
                ),
                "candidates": c,
            }

        rows.append(
            {
                "rate_hz": rate,
                "edge": edge,
                "provenance": provenance,
                "reference_positive": bool(reference),
                "fit": asdict(fit),
                "raw": evidence(raw),
                "residual": evidence(residual),
            }
        )

    for probe in json.loads((inputs_dir / "inputs.json").read_text()):
        if "session_id" not in probe["provenance"]:
            continue
        path = inputs_dir / probe["file"]
        if path.name != probe["file"] or digest(path) != probe["sha256"]:
            raise ValueError("probe identity changed")
        values, _, rate, edge, counter = read_probe(path)
        if (
            rate != probe["rate_hz"]
            or edge != int(probe["edge"] == "upper")
            or str(counter) != probe["device_counter"]
        ):
            raise ValueError("probe header mismatch")
        reference = [c for c in probe["oracle_candidates"] if c["margin"] >= 0.025]
        run(values, rate, probe["edge"], {"kind": "RF", "probe": probe["file"]}, reference)
        if reference:
            amplitude = np.sqrt(
                np.mean(np.abs(values) ** 2) * policy["mixed_rf_tone_to_original_power_ratio"]
            )
            tone = amplitude * np.exp(
                2j * np.pi * policy["mixed_rf_frequency_hz"] * np.arange(len(values)) / rate
            )
            run(
                values + tone,
                rate,
                probe["edge"],
                {"kind": "RF+tone", "probe": probe["file"]},
                reference,
            )
    rng = np.random.default_rng(policy["noise_seed"])
    for rate in (2500000, 5000000):
        for edge in ("lower", "upper"):
            for frequency in policy["control_frequencies_hz"]:
                for amplitude in policy["control_amplitudes"]:
                    noise = rng.normal(size=rate // 50) + 1j * rng.normal(size=rate // 50)
                    tone = amplitude * np.exp(2j * np.pi * frequency * np.arange(len(noise)) / rate)
                    run(
                        noise + tone,
                        rate,
                        edge,
                        {"kind": "tone_control", "frequency_hz": frequency, "amplitude": amplitude},
                        [],
                    )
    write_json(output / "results.json", rows)
    for rate in (2500000, 5000000):
        for kind in ("RF", "RF+tone", "tone_control"):
            selected = [r for r in rows if r["rate_hz"] == rate and r["provenance"]["kind"] == kind]
            print(
                rate,
                kind,
                "n",
                len(selected),
                "fit",
                sum(r["fit"]["applied"] for r in selected),
                "raw/clean flags",
                [sum(r[k]["detected"] for r in selected) for k in ("raw", "residual")],
                "raw/clean associated",
                [sum(r[k]["reference_associated"] for r in selected) for k in ("raw", "residual")],
                flush=True,
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    evaluate(args.inputs, args.output)


if __name__ == "__main__":
    main()
