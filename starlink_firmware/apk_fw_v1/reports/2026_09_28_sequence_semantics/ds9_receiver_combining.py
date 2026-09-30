"""Validate simple receiver combining against held-out repeating-sequence signs."""

import hashlib
import json
from pathlib import Path

import numpy as np
from region_phase_audit import WORDS

BASE = Path(__file__).resolve().parent


def design(a, b):
    return np.stack([a.real, a.imag, b.real, b.imag, np.ones(a.shape)], axis=-1)


def fit(x, y):
    return np.stack(
        [
            np.linalg.lstsq(x[:, :, k].reshape(-1, 5), y[:, :, k].ravel(), rcond=None)[0]
            for k in range(x.shape[2])
        ]
    )


def main():
    physical = [
        int(k)
        for k in np.argsort(np.fft.fftfreq(1024))
        if 2 <= k < 1022 and k not in range(488, 496) and k not in range(528, 536)
    ]
    compact = {b: i for i, b in enumerate(physical)}
    datasets, hashes = {}, {}
    for tag in ("middle", "last"):
        source = BASE / f"local/DS9-{tag}-soft.npz"
        word_path = BASE / (
            "local/ds9_word_audit.json" if tag == "middle" else "local/ds9_last_word_audit.json"
        )
        a = np.load(source)
        assert np.array_equal(a["bins0"], a["bins1"])
        phases = {}
        for r in json.loads(word_path.read_text())["rows"]:
            if r["accepted"] and r["phase"] is not None and r["last_symbol"] < 242:
                assert r["frame"] not in phases or phases[r["frame"]] == r["phase"]
                phases[r["frame"]] = r["phase"]
        frames = sorted(phases)
        slots = (
            np.array([compact[int(b)] for b in a["bins0"]])[None, :]
            - 16 * np.arange(242, 302)[:, None]
        ) % 60
        expected = WORDS[np.array([phases[f] for f in frames])[:, None, None], slots[None]]
        x = design(a["z0"][frames, 240:300], a["z1"][frames, 240:300])
        split = len(frames) // 2
        coefficients = fit(x[:split, :30], expected[:split, :30])
        choice = np.argmin(
            np.stack(
                [
                    ((x[:split, :30, :, k] >= 0) != (expected[:split, :30] >= 0)).mean(axis=(0, 1))
                    for k in (0, 2)
                ]
            ),
            axis=0,
        )
        datasets[tag] = dict(
            x=x[split:, 30:],
            expected=expected[split:, 30:],
            coefficients=coefficients,
            choice=choice,
            bins=a["bins0"],
            train=frames[:split],
            evaluation=frames[split:],
        )
        header_path = BASE / f"local/DS9-{tag}-combined-header.npz"
        header = (a["z0"][:, :6] + a["z1"][:, :6]) / 2
        np.savez_compressed(
            header_path,
            soft=header,
            bits=(header.real >= 0).astype(np.uint8),
            bins=a["bins0"],
            ofdm_symbols=np.arange(2, 8),
            evaluation_frames=np.array(frames[split:]),
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            limitation="Equal-weight soft estimate, not validated header bits or plaintext.",
        )
        datasets[tag]["header_output"] = str(header_path)
        datasets[tag]["header_sha256"] = hashlib.sha256(header_path.read_bytes()).hexdigest()
        for p in (source, word_path):
            hashes[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    assert np.array_equal(datasets["middle"]["bins"], datasets["last"]["bins"])
    rows = []
    for tag, d in datasets.items():
        x, truth = d["x"], d["expected"] >= 0
        predictions = dict(
            rx0=x[..., 0],
            rx1=x[..., 2],
            equal=x[..., 0] + x[..., 2],
            discovery_selected_rx=np.where(d["choice"][None, None, :] == 0, x[..., 0], x[..., 2]),
        )
        for fit_tag, model in datasets.items():
            predictions[f"linear_from_{fit_tag}"] = np.sum(
                x * model["coefficients"][None, None], axis=-1
            )
        errors = {name: int(((p >= 0) != truth).sum()) for name, p in predictions.items()}
        row = dict(
            tag=tag,
            count=int(truth.size),
            errors=errors,
            discovery_frames=d["train"],
            evaluation_frames=d["evaluation"],
            coefficients=d["coefficients"].tolist(),
            bins=d["bins"].tolist(),
            header_output=d["header_output"],
            header_sha256=d["header_sha256"],
        )
        rows.append(row)
        print(json.dumps(dict(tag=tag, count=int(truth.size), errors=errors), indent=2))
    output = dict(
        rows=rows,
        input_sha256=hashes,
        limitation="Sequence phase inferred in earlier paired windows; agreement "
        "with model signs, not independent transmitter BER. Per-carrier least "
        "squares coefficients fit only first22frames symbols242–271; evaluate "
        "last23frames symbols272–301, including transfer across visits. Five "
        "coefficients/carrier, no tuning on evaluation. Does not validate header "
        "semantics or header combination accuracy; native caches unchanged.",
    )
    (BASE / "local/ds9_receiver_combining.json").write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
