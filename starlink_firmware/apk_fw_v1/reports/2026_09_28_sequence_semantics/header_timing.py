"""Test literal binary frame-counter bits in cached UT early-header slices."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]
SOURCE = (BASE.parents[3] / "reports") / "2026_09_28_ds7_ds8_correspondence/local/ut-codebook"


def counter_models(ticks, max_bit=9):
    """All phases of each square-wave counter bit; complements fitted separately."""
    models, descriptions = [], []
    for bit in range(max_bit + 1):
        for offset in range(2**bit):
            models.append(2 * (((ticks + offset) >> bit) & 1) - 1)
            descriptions.append(dict(bit=bit, offset=offset))
    return np.array(models, float).T, descriptions


def fit_positions(bits, valid, ticks):
    models, descriptions = counter_models(ticks)
    n = len(ticks)
    train = np.arange(n) < int(n * 0.6)
    validation = (np.arange(n) >= int(n * 0.6)) & (np.arange(n) < int(n * 0.8))
    test = np.arange(n) >= int(n * 0.8)
    rows = []
    for pos in range(bits.shape[1]):
        tr, va, te = [mask & valid[:, pos] for mask in [train, validation, test]]
        if min(tr.sum(), va.sum(), te.sum()) < 20:
            continue
        # Exclude near-constant models that merely relabel the majority baseline.
        eligible = (abs(models[tr].mean(axis=0)) <= 0.8) & (abs(models[va].mean(axis=0)) <= 0.8)
        correlations = (models[tr] * bits[tr, pos, None]).mean(axis=0)
        polarity = np.where(correlations >= 0, 1, -1)
        validation_accuracy = (models[va] * polarity == bits[va, pos, None]).mean(axis=0)
        validation_accuracy[~eligible] = -1
        if not eligible.any():
            continue
        selected = int(np.argmax(validation_accuracy))
        baseline = 1 if bits[tr, pos].mean() >= 0 else -1
        rows.append(
            dict(
                position=pos,
                **descriptions[selected],
                polarity=int(polarity[selected]),
                discovery_n=int(tr.sum()),
                validation_n=int(va.sum()),
                test_n=int(te.sum()),
                discovery_accuracy=float((1 + abs(correlations[selected])) / 2),
                validation_accuracy=float(validation_accuracy[selected]),
                test_accuracy=float(
                    np.mean(models[te, selected] * polarity[selected] == bits[te, pos])
                ),
                test_baseline=float(np.mean(bits[te, pos] == baseline)),
            )
        )
    return rows


def main():
    timepath = SOURCE / "timing-metadata.npz"
    times = np.load(timepath)["TOAs"].ravel()
    gaps = np.diff(times) * 750
    boundaries = np.flatnonzero(abs(gaps - np.rint(gaps)) > 0.05) + 1
    segment = max(np.split(np.arange(len(times)), boundaries), key=len)
    ticks = np.rint((times[segment] - times[segment[0]]) * 750).astype(int)
    assert np.max(abs((times[segment] - times[segment[0]]) * 750 - ticks)) < 0.05
    templatepath = (
        ROOT
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement/reference-template"
        / "referenceTemplate.mat"
    )
    template = np.exp(0.5j * np.pi * loadmat(templatepath)["referenceTemplateRotations"])
    pieces, bins = [], []
    inputs = [timepath, templatepath]
    for first in [100, 200]:
        path = SOURCE / f"bins-{first}.npz"
        inputs.append(path)
        archive = np.load(path)
        pieces.append(archive["symbols"][segment, 1:7] * template[archive["bins"], 1:7].T.conj())
        bins.extend(archive["bins"].tolist())
    z = np.concatenate(pieces, axis=-1)
    valid = np.isfinite(z) & (abs(z.imag) < 0.05) & (abs(abs(z.real) - 1) < 0.05)
    bits = np.where(z.real >= 0, 1, -1)
    rows = fit_positions(bits.reshape(len(ticks), -1), valid.reshape(len(ticks), -1), ticks)
    for row in rows:
        row.update(
            symbol=2 + row["position"] // len(bins), carrier=bins[row["position"] % len(bins)]
        )
    selected = max(rows, key=lambda row: row["validation_accuracy"])
    result = dict(
        segment_frame_indices=[int(segment[0]), int(segment[-1])],
        frames=len(segment),
        tick_span=[int(ticks[0]), int(ticks[-1])],
        positions_tested=len(rows),
        model_count=1023,
        selected_by_validation=selected,
        positions=rows,
        input_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        scope="OFDM 2..7, eight cached carriers, longest continuous TOA segment. "
        "Chronological 60/20/20 split; counter bits 0..9 with every nonredundant "
        "offset and fitted polarity. Uses actual 750 Hz frame ticks, not array indices.",
        limitations="Exploratory previously inspected reference. Unknown field coding, "
        "interleaving, other carriers and longer counters are not excluded. "
        "Candidate selection precedes test evaluation; no CRC or FEC validation.",
    )
    (BASE / "local/header_timing.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ["positions", "input_sha256"]}, indent=2
        )
    )


if __name__ == "__main__":
    main()
