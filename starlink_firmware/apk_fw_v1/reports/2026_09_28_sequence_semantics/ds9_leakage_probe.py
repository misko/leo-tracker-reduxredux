"""Predict shared tail residuals from known adjacent-carrier constellation patterns."""

import hashlib
import json
from pathlib import Path

import numpy as np
from region_phase_audit import WORDS
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent


def fit_predict(design, values, train, evaluation):
    x = design[train].reshape(-1, design.shape[-1])
    y = values[train].ravel()
    coefficients = np.linalg.lstsq(x, y, rcond=None)[0]
    return design[evaluation] @ coefficients, coefficients


def main():
    source = BASE / "local/DS9-middle-soft.npz"
    words_path = BASE / "local/ds9_word_audit.json"
    template_path = (
        BASE.parents[3]
        / "docs/research/starlink-literature/local/data/ut-pilots"
        / "supplement/reference-template/referenceTemplate.mat"
    )
    archive = np.load(source)
    bins = archive["bins0"]
    assert np.array_equal(bins, archive["bins1"])
    phases = {}
    for row in json.loads(words_path.read_text())["rows"]:
        if row["accepted"] and row["phase"] is not None and row["last_symbol"] < 272:
            if row["frame"] in phases:
                assert phases[row["frame"]] == row["phase"]
            phases[row["frame"]] = row["phase"]
    frames = sorted(phases)
    split = len(frames) // 2
    train, evaluation = np.arange(split), np.arange(split, len(frames))
    symbols = np.arange(272, 302)
    physical = [
        k
        for k in np.argsort(np.fft.fftfreq(1024))
        if 2 <= k < 1022 and k not in range(488, 496) and k not in range(528, 536)
    ]
    compact = {int(k): i for i, k in enumerate(physical)}
    # Identical target carriers across all models; exclude neighborhoods containing pilots.
    targets = [int(k) for k in bins if all(k + d in compact for d in range(-4, 5))]
    template = loadmat(template_path)["referenceTemplateRotations"]
    rows = []
    for radius in (0, 1, 2, 4):
        residuals, originals = [[], []], [[], []]
        for target in targets:
            features = [np.ones((len(frames), len(symbols)), complex)]
            for offset in range(-radius, radius + 1):
                neighbor = target + offset
                slots = (compact[neighbor] - 16 * symbols) % 60
                signs = WORDS[np.array([phases[f] for f in frames])[:, None], slots[None]]
                rotation = np.exp(
                    0.5j * np.pi * (template[neighbor, symbols - 1] - template[target, symbols - 1])
                )
                features.append(signs * rotation)
            design = np.stack(features, axis=-1)
            column = int(np.flatnonzero(bins == target)[0])
            for rx in range(2):
                values = archive[f"z{rx}"][frames][:, symbols - 2, column]
                predicted, _ = fit_predict(design, values, train, evaluation)
                originals[rx].append(values[evaluation])
                residuals[rx].append(values[evaluation] - predicted)
        before, after = [np.array(v) for v in originals], [np.array(v) for v in residuals]
        raw_cross = float(np.mean(before[0].imag * before[1].imag))
        residual_cross = float(np.mean(after[0].imag * after[1].imag))
        rows.append(
            dict(
                radius=radius,
                complex_coefficients_per_carrier=2 * radius + 2,
                raw_imaginary_cross_power=raw_cross,
                residual_imaginary_cross_power=residual_cross,
                cross_power_reduction=1 - residual_cross / raw_cross,
                imaginary_power_reduction=[
                    float(1 - np.mean(b.imag**2) / np.mean(a.imag**2))
                    for a, b in zip(before, after, strict=True)
                ],
            )
        )
    result = dict(
        rows=rows,
        discovery_frames=[frames[i] for i in train],
        evaluation_frames=[frames[i] for i in evaluation],
        symbols=symbols.tolist(),
        target_bins=targets,
        phase_source="Only accepted windows ending before symbol272",
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (source, words_path, template_path)
        },
        limitation="Exploratory linear same-symbol nearest-carrier model, coefficients "
        "fit separately per receiver/carrier using chronological discovery frames. "
        "Earlier windows in evaluation frames provide phase; no evaluation tail "
        "samples fit coefficients. Shared interference/model error may remain. "
        "Predictability is not proof of a physical cause or semantic bit decode.",
    )
    (BASE / "local/ds9_leakage_probe.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["rows"], indent=2))
    print("split", split, len(evaluation), "carriers", len(targets))


if __name__ == "__main__":
    main()
