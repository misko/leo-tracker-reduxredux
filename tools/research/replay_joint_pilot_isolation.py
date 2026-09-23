"""Bounded six-snippet joint pilot replay; run only after protocol freeze."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from leo.analysis.starlink.templates import (
    CYCLIC_PREFIX_DURATION_S,
    OFDM_SYMBOL_DURATION_S,
    edge_frequencies_hz,
    qin_edge_pilot_symbols,
)
from leo.storage import RecordingStore
from tools.research.joint_template_source_isolation import fit_templates, seeded_group_split

ROOT = Path(__file__).resolve().parents[2]
INPUT = (
    ROOT
    / "reports/figures/2026_09_23_independent_phase/geometry-sensitivity"
    / "raw-candidate-opportunities.json"
)
FS = 2_500_000
COUNT = 50_000


def tones(epoch: int, frequency: float, roll: int = 0) -> np.ndarray:
    """Eight pilot columns on independently rounded frame starts, chunk phase origin."""
    result = np.zeros((8, COUNT), dtype=np.complex128)
    states = qin_edge_pilot_symbols("upper", symbol_roll=roll)
    frequencies = edge_frequencies_hz("upper")
    for k in range(-20, 21):
        start = epoch + round(k * FS / 750)
        lo, hi = max(0, start), min(COUNT, start + round(FS / 750))
        if hi <= lo:
            continue
        indexes = np.arange(lo, hi)
        local = (indexes - start) / FS
        symbol = np.floor(local / OFDM_SYMBOL_DURATION_S).astype(int)
        valid = (symbol >= 2) & (symbol < 302)
        indexes, local, symbol = indexes[valid], local[valid], symbol[valid]
        offset = local - symbol * OFDM_SYMBOL_DURATION_S - CYCLIC_PREFIX_DURATION_S
        result[:, indexes] = (
            states[symbol - 2].T
            * np.exp(2j * np.pi * frequencies[:, None] * offset)
            * np.exp(2j * np.pi * frequency * indexes / FS)
            / np.sqrt(8)
        )
    return result


def serial(value):
    if isinstance(value, complex):
        return [value.real, value.imag]
    raise TypeError(type(value).__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    doc = json.loads(INPUT.read_text())
    sources = [
        Path(__file__),
        ROOT / "tools/research/joint_template_source_isolation.py",
        ROOT / "src/leo/analysis/starlink/templates.py",
        INPUT,
        ROOT / "reports/2026_09_23_joint_pilot_isolation_protocol.md",
    ]
    binding = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
    }
    (args.output / "binding.json").write_text(json.dumps(binding, indent=2) + "\n")
    store = RecordingStore.open_read_only(Path("/srv/bulk/leo"))
    try:
        bundle = store.inspect(doc["session_id"])
        reader = store.reader(bundle, "stream-1", verify=True)
        for index, opportunity in enumerate(doc["opportunities"]):
            matched = [
                m
                for m in opportunity["one_to_one_component_matchings"]
                if m["both_pairs_timing_compatible"]
            ]
            if len(matched) != 1:
                raise ValueError("matching is not unique")
            matching = matched[0]
            picks = {}
            for rx in (0, 1):
                picks[rx] = [
                    min(
                        opportunity["receiver_components"][str(rx)][c],
                        key=lambda r: r["candidate_rank"],
                    )
                    for c in matching[f"rx{rx}_component_indices"]
                ]
            raw = reader.read(opportunity["sample_start"], COUNT, receiver_ids=(0, 1))
            iq = (raw[:, :, 0].astype(float) + 1j * raw[:, :, 1].astype(float)) / 32768
            n = np.arange(COUNT)
            split = seeded_group_split(n // 250, seed=20260925 + index)
            guard = (n % 250 >= 16) & (n % 250 < 234)
            row = dict(
                sample_start=opportunity["sample_start"],
                time_s=opportunity["time_s"],
                raw_sha256=hashlib.sha256(raw.tobytes()).hexdigest(),
                training_group_ids=np.unique((n // 250)[split]).tolist(),
                nominees=picks,
                receivers={},
            )
            for rx in (0, 1):
                start_time = time.monotonic()
                a, b = picks[rx]
                exact = np.array(
                    [tones(int(p["local_epoch_sample"]), p["tracking_cfo_hz"]) for p in (a, b)]
                )
                rolled = np.array(
                    [tones(int(p["local_epoch_sample"]), p["tracking_cfo_hz"], 17) for p in (a, b)]
                )
                swapped = np.array(
                    [
                        tones(int(q["local_epoch_sample"]), p["tracking_cfo_hz"])
                        for p, q in ((a, b), (b, a))
                    ]
                )
                mask = guard
                models = {
                    "exact_ab": exact,
                    "single_a": exact[:1],
                    "single_b": exact[1:],
                    "exact_a_rolled_b": np.array([exact[0], rolled[1]]),
                    "rolled_a_exact_b": np.array([rolled[0], exact[1]]),
                    "both_rolled": rolled,
                    "swapped_epochs": swapped,
                }
                fitted = {}
                for name, model in models.items():
                    fitted[name] = asdict(
                        fit_templates(
                            iq[mask, rx], model[:, :, mask], n[mask], split[mask], sample_rate_hz=FS
                        )
                    )
                    print(index, rx, name, fitted[name]["held_sse"], flush=True)
                held_energy = float(np.sum(abs(iq[mask & ~split, rx]) ** 2))
                row["receivers"][str(rx)] = dict(
                    models=fitted,
                    held_energy=held_energy,
                    train_indices_sha256=hashlib.sha256(
                        n[mask & split].astype("<i8").tobytes()
                    ).hexdigest(),
                    held_indices_sha256=hashlib.sha256(
                        n[mask & ~split].astype("<i8").tobytes()
                    ).hexdigest(),
                    elapsed_s=time.monotonic() - start_time,
                )
            (args.output / f"probe-{index}.json").write_text(
                json.dumps(row, default=serial, indent=2) + "\n"
            )
    finally:
        store.close()


if __name__ == "__main__":
    main()
