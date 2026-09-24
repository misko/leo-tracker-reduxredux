"""Seeded development replay of local two-source differential phase stability."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from leo.storage import RecordingStore
from tools.research.joint_template_source_isolation import _design, seeded_group_split
from tools.research.replay_joint_pilot_isolation import FS, ROOT, tones

COUNT = 50_000
SEED = 20260929
GROUP = 250
GUARD = 16


def circular_fit(times: np.ndarray, phases: np.ndarray) -> tuple[float, float]:
    """Fit an affine unwrapped phase using chronological training observations."""
    order = np.argsort(times)
    x = times[order]
    y = np.unwrap(phases[order])
    slope, intercept = np.polyfit(x - x.mean(), y, 1)
    return float(intercept - slope * x.mean()), float(slope)


def circular_score(times: np.ndarray, phases: np.ndarray, fit: tuple[float, float]) -> dict:
    residual = np.angle(np.exp(1j * (phases - (fit[0] + fit[1] * times))))
    return {
        "rms_rad": float(np.sqrt(np.mean(residual**2))),
        "resultant": float(abs(np.mean(np.exp(1j * residual)))),
        "residual_rad": residual.tolist(),
    }


def coefficient_phases(iq, templates, indices, frequencies, train_groups):
    """Extract group coefficients and training-only coefficient-vector gauges."""
    groups = np.unique(indices // GROUP)
    coefficients = np.empty((2, 2, len(groups), 8), complex)
    conditions = []
    for rx in (0, 1):
        for gi, group in enumerate(groups):
            take = indices // GROUP == group
            design = _design(templates[rx][:, :, take], indices[take], frequencies[rx], FS)
            value, _, rank, singular = np.linalg.lstsq(design, iq[take, rx], rcond=None)
            if rank != 16 or singular[0] / singular[-1] > 1e6:
                raise ValueError("group design is rank deficient or ill conditioned")
            conditions.append(float(singular[0] / singular[-1]))
            coefficients[rx, :, gi] = value.reshape(2, 8)
    train = np.isin(groups, train_groups)
    scalar = np.empty((2, 2, len(groups)), complex)
    for rx in (0, 1):
        for source in (0, 1):
            # Principal coefficient shape fixes only a training-derived gauge.
            _, _, vh = np.linalg.svd(coefficients[rx, source, train], full_matrices=False)
            reference = vh[0].conj()
            scalar[rx, source] = coefficients[rx, source] @ reference.conj()
    cross_rx = scalar[1] * scalar[0].conj()
    phase = np.angle(cross_rx[0] * cross_rx[1].conj())
    coherence = abs(scalar) / np.linalg.norm(coefficients, axis=-1)
    return groups, phase, coherence, max(conditions)


def analyze(iq, nominees, frequencies, train_groups):
    n = np.arange(COUNT)
    mask = (n % GROUP >= GUARD) & (n % GROUP < GROUP - GUARD)
    indices = n[mask]
    results = {}
    for name, roll, swap in (("exact", 0, False), ("rolled", 17, False), ("swapped", 0, True)):
        templates = []
        for rx in (0, 1):
            picks = nominees[str(rx)]
            epochs = [int(p["local_epoch_sample"]) for p in picks]
            if swap:
                epochs.reverse()
            templates.append(
                [tones(epochs[s], picks[s]["tracking_cfo_hz"], roll)[:, mask] for s in (0, 1)]
            )
        groups, phase, coherence, maximum_condition = coefficient_phases(
            iq[mask], np.asarray(templates), indices, frequencies, train_groups
        )
        train = np.isin(groups, train_groups)
        time = (groups * GROUP + GROUP / 2) / FS
        affine = circular_fit(time[train], phase[train])
        constant = (
            circular_fit(np.zeros(train.sum()), phase[train])
            if False
            else (float(np.angle(np.mean(np.exp(1j * phase[train])))), 0.0)
        )
        results[name] = {
            "affine_fit": {"intercept_rad": affine[0], "slope_rad_s": affine[1]},
            "held_affine": circular_score(time[~train], phase[~train], affine),
            "held_constant": circular_score(time[~train], phase[~train], constant),
            "minimum_scalar_coherence": float(np.min(coherence[:, :, ~train])),
            "maximum_group_design_condition": maximum_condition,
            "group_phase_rad": phase.tolist(),
        }
    exact = results["exact"]["held_affine"]
    results["decision"] = {
        "criterion": "exact resultant >= 0.8 and exact RMS below rolled and swapped controls",
        "supported": bool(
            exact["resultant"] >= 0.8
            and exact["rms_rad"] < results["rolled"]["held_affine"]["rms_rad"]
            and exact["rms_rad"] < results["swapped"]["held_affine"]["rms_rad"]
        ),
    }
    return groups, results


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seal", type=Path, required=True)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sources = [
        Path(__file__),
        ROOT / "tools/research/replay_joint_pilot_isolation.py",
        ROOT / "tools/research/joint_template_source_isolation.py",
        ROOT / "src/leo/analysis/starlink/templates.py",
        ROOT / "reports/2026_09_23_local_differential_phase_protocol.md",
        ROOT / "reports/figures/2026_09_23_joint_pilot_isolation/probe-4.json",
        ROOT / "reports/figures/2026_09_23_shared_receiver_cfo_nested/probe-4.json",
    ]
    if args.freeze:
        if args.seal.exists():
            raise ValueError("seal exists")
        args.seal.parent.mkdir(parents=True, exist_ok=True)
        args.seal.write_text(
            json.dumps({str(p.relative_to(ROOT)): digest(p) for p in sources}, indent=2) + "\n"
        )
        return
    if args.output is None:
        raise ValueError("output required")
    seal = json.loads(args.seal.read_text())
    for name, expected in seal.items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"sealed input changed: {name}")
    original = json.loads(sources[-2].read_text())
    nested = json.loads(sources[-1].read_text())
    frequencies = np.asarray(nested["independent"]["residual_cfo_hz"])
    n = np.arange(COUNT)
    split = seeded_group_split(n // GROUP, seed=SEED)
    train_groups = np.unique((n // GROUP)[split])
    mask = (n % GROUP >= GUARD) & (n % GROUP < GROUP - GUARD)
    for label, support in (("train", mask & split), ("held", mask & ~split)):
        got = hashlib.sha256(n[support].astype("<i8").tobytes()).hexdigest()
        expected = original["receivers"]["0"][f"{label}_indices_sha256"]
        if got != expected or expected != original["receivers"]["1"][f"{label}_indices_sha256"]:
            raise ValueError("seeded split does not match frozen replay")
    store = RecordingStore.open_read_only(Path("/srv/bulk/leo"))
    try:
        reader = store.reader(
            store.inspect("cap-20260825T010019-89c2889553e0"), "stream-1", verify=True
        )
        raw = reader.read(original["sample_start"], COUNT, receiver_ids=(0, 1))
    finally:
        store.close()
    if hashlib.sha256(raw.tobytes()).hexdigest() != original["raw_sha256"]:
        raise ValueError("saved snippet changed")
    iq = (raw[:, :, 0].astype(float) + 1j * raw[:, :, 1].astype(float)) / 32768
    groups, results = analyze(iq, original["nominees"], frequencies, train_groups)
    nominal = np.asarray(
        [[p["tracking_cfo_hz"] for p in original["nominees"][str(rx)]] for rx in (0, 1)]
    )
    closure_hz = float(np.diff((nominal + frequencies)[1] - (nominal + frequencies)[0])[0] * -1)
    results["exact"]["template_double_difference_rate_rad_s"] = 2 * np.pi * closure_hz
    results["exact"]["restored_double_difference_rate_rad_s"] = (
        results["exact"]["affine_fit"]["slope_rad_s"] + 2 * np.pi * closure_hz
    )
    output = {
        "schema": "local-differential-phase-development/v1",
        "time_s": original["time_s"],
        "sample_start": original["sample_start"],
        "seed": SEED,
        "training_group_ids": train_groups.tolist(),
        "held_group_ids": [int(g) for g in groups if g not in set(train_groups)],
        "independent_residual_cfo_hz": frequencies.tolist(),
        "results": results,
        "limitations": (
            "reused development IQ; conditional on frozen nominees, epochs, aliases, and CFOs"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
