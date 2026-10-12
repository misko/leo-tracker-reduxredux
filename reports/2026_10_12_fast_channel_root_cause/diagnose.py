"""Read verified scientific ports and diagnose receiver/channel-group calibration."""

import argparse
import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from leo.analysis.hard60_score import likelihood, predict_orbits
from leo.analysis.regional_position_bank import build_regional_bank
from leo.application.hard60_runner import HARD60_SCORE
from leo.application.regional_position_inputs import prepare_position_windows
from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.regional_position import RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets


def load_source(parent):
    path = Path("/opt/leo-fast-auto/20261011-r3/bin/fast_scan_standard_pipeline.py")
    spec = importlib.util.spec_from_file_location("adapter", path)
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    return adapter.load_tracking_input(json.loads((parent / "input/tracking.json").read_text()))


def subset_source(source, case):
    channels = {"ch1-4": range(1, 5), "ch5-8": range(5, 9)}[case]
    binding = canonical_digest(
        {
            "parent_input": source.input_manifest_sha256,
            "parent_analysis": source.analysis_manifest_sha256,
            "channels": list(channels),
            "policy": "channel-subset-v1",
        }
    )
    return replace(
        source,
        probes=tuple(p for p in source.probes if p.channel in channels),
        input_manifest_sha256=binding,
    )


def row_keys(obs):
    return [
        (round(float(t), 8), int(rx), int(ch))
        for t, rx, ch in zip(obs.times_s, obs.receiver, obs.channel, strict=True)
    ]


def reconstruct(doc, observations, bank):
    fit = doc["diagnostics"]["b7"]["attempts"]["B4W"]["fitted-c"]
    state = fit["joint_state"]
    vector = np.asarray(fit["vector"])
    numbers = doc["methods"][0]["arms"][0]["selected"]["satellites"]
    assert len(vector) == 7 + len(numbers)
    lookup = {int(n): i for i, n in enumerate(bank.numbers)}
    subset = bank.select([lookup[n] for n in numbers])
    from leo.analysis.regional_position_score import zero_sum_basis

    shifts = vector[7] + zero_sum_basis(len(numbers)) @ vector[8:]
    prediction, visible, _, _ = predict_orbits(
        subset, observations, RegionalPrior(), vector[:2], shifts
    )
    times = observations.times_s - observations.time_center_s
    rx = observations.receiver
    design = np.column_stack(
        [
            rx == 0,
            (rx == 0) * times,
            rx == 1,
            (rx == 1) * times,
            (observations.rf_hz - observations.rf_center_hz) / 1e9,
        ]
    )
    nodes = np.asarray(state["clock_nodes_s"])
    knots = np.asarray(state["clock_knots_hz"])
    clocks = np.array(
        [np.interp(t, nodes, knots[r]) for t, r in zip(observations.times_s, rx, strict=True)]
    )
    baseline = np.asarray(state["receiver_baseline_hz"])
    assert baseline.shape == rx.shape
    correction = baseline + design @ vector[2:7] + clocks
    terms = likelihood(
        observations.measured_hz, prediction + correction[:, None], visible, HARD60_SCORE
    )
    mass = terms.responsibilities.sum()
    rms = np.sqrt(np.sum(terms.responsibilities * terms.residual_hz**2) / mass)
    assert np.isclose(rms, fit["posterior_rms_hz"], atol=1e-6)
    lines = []
    for receiver in (0, 1):
        mask = rx == receiver
        x = np.column_stack([np.ones(mask.sum()), observations.times_s[mask] - 150])
        coef = np.linalg.lstsq(x, baseline[mask], rcond=None)[0]
        # The joint baseline is the frozen affine calibration after knot subtraction.
        error = baseline[mask] - x @ coef
        assert np.max(abs(error)) < 1e-5
        offset = (
            coef[0]
            + vector[2 + 2 * receiver]
            + vector[3 + 2 * receiver] * (150 - observations.time_center_s)
            + vector[6] * (11584687500 - observations.rf_center_hz) / 1e9
            + np.interp(150, nodes, knots[receiver])
        )
        lines.append(
            dict(
                receiver=receiver,
                offset_at_150s_11_5846875ghz_hz=float(offset),
                slope_hz_s=float(coef[1] + vector[3 + 2 * receiver]),
                c_hz_per_ghz=float(vector[6]),
            )
        )
    return dict(
        numbers=numbers,
        vector=vector,
        shifts=shifts,
        correction=correction,
        responsibilities=terms.responsibilities,
        residual_hz=terms.residual_hz,
        prediction=prediction,
        visible=visible,
        lines=lines,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    source = load_source(args.parent)
    full = prepare_position_windows(source)
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = archive.select_latest_before(full.start_utc_ns - 505_000_000_000)
    catalogue = parse_element_sets(archive.read(snapshot))
    indices = np.array(
        [i for i, n in enumerate(catalogue.names) if n.upper().startswith("STARLINK")]
    )
    bank, receipt = build_regional_bank(
        catalogue,
        indices,
        full.start_utc_ns,
        full.observations,
        RegionalPrior(),
        maximum_seconds=180,
    )
    full_keys = row_keys(full.observations)
    lookup = {k: i for i, k in enumerate(full_keys)}
    arrays = {
        "times_s": full.observations.times_s,
        "measured_hz": full.observations.measured_hz,
        "rf_hz": full.observations.rf_hz,
        "receiver": full.observations.receiver,
        "channel": full.observations.channel,
        "margin": full.observations.margin,
        "window_ids": np.asarray(full.observations.window_ids),
        "numbers": bank.numbers,
        "nodes_s": bank.nodes_s,
        "position_km": bank.position_km,
        "velocity_km_s": bank.velocity_km_s,
    }
    info = {
        "input_sha256": source.input_manifest_sha256,
        "analysis_sha256": source.analysis_manifest_sha256,
        "tle_sha256": snapshot.digest,
        "cases": {},
        "offset_contrast": [],
    }
    mapped = []
    for case in ("ch1-4", "ch5-8", "ch1-8"):
        observations = (
            full.observations
            if case == "ch1-8"
            else prepare_position_windows(subset_source(source, case)).observations
        )
        doc = json.loads((args.parent / case / "regional.json").read_text())
        fit = reconstruct(doc, observations, bank)
        ix = np.array([lookup[k] for k in row_keys(observations)])
        np.testing.assert_allclose(
            full.observations.measured_hz[ix], observations.measured_hz, atol=0
        )
        mapped.extend(ix.tolist()) if case != "ch1-8" else None
        prefix = case.replace("-", "_")
        for key in (
            "vector",
            "shifts",
            "correction",
            "responsibilities",
            "residual_hz",
            "prediction",
            "visible",
        ):
            arrays[prefix + "_" + key] = fit[key]
        arrays[prefix + "_numbers"] = np.asarray(fit["numbers"])
        arrays[prefix + "_rows"] = ix
        info["cases"][case] = {
            "lines": fit["lines"],
            "satellites": fit["numbers"],
            "windows": len(ix),
            "selected": {
                k: v
                for k, v in doc["methods"][0]["arms"][0]["selected"].items()
                if k != "joint_state"
            },
        }
    assert sorted(mapped) == list(range(len(full_keys)))
    for rx in (0, 1):
        low = info["cases"]["ch1-4"]["lines"][rx]
        high = info["cases"]["ch5-8"]["lines"][rx]
        info["offset_contrast"].append(
            dict(
                receiver=rx,
                high_minus_low_hz=high["offset_at_150s_11_5846875ghz_hz"]
                - low["offset_at_150s_11_5846875ghz_hz"],
                high_minus_low_slope_hz_s=high["slope_hz_s"] - low["slope_hz_s"],
            )
        )
    np.savez_compressed(args.output / "diagnostic-arrays.npz", **arrays)
    info["arrays_sha256"] = sha256_digest((args.output / "diagnostic-arrays.npz").read_bytes())
    (args.output / "diagnostics.json").write_text(json.dumps(info, indent=2) + "\n")
    print(json.dumps(info["offset_contrast"]), flush=True)


if __name__ == "__main__":
    main()
