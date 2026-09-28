"""Map pilot-referenced header signs and test discovery-selected repetition lags."""

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from rest_signal import split_word, stability

OUT = Path(__file__).parent / "local"


def lag_correlation(values, valid, lag):
    keep = valid[:-lag] & valid[lag:]
    a, b = values[:-lag][keep], values[lag:][keep]
    if len(a) < 50 or min(np.std(a), np.std(b)) == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def main():
    path = OUT / "pilot_polarity.npz"
    archive = np.load(path)
    z, bins = archive["deviations"][:, :, :6], archive["bins"]
    order = np.argsort(np.fft.fftfreq(1024)[bins])
    unit = z / np.maximum(abs(z), 1e-12)
    signs = np.where(z.real >= 0, 1, -1)
    valid = (abs(unit.real) > 0.9).all(axis=1) & (signs[:, 0] == signs[:, 1])
    bits = signs[:, 0]
    score = stability(bits, valid)
    tests = []
    ordered, good = bits[:, :, order], valid[:, :, order]
    for symbol in range(6):
        differences = [ordered[f, symbol] * ordered[f + 1, symbol] for f in [0, 2, 4]]
        masks = [good[f, symbol] & good[f + 1, symbol] for f in [0, 2, 4]]
        lags = range(1, 501)
        scores = [lag_correlation(differences[0], masks[0], lag) for lag in lags]
        chosen = int(np.argmax(np.abs(scores))) + 1
        tests.append(
            dict(
                symbol=symbol + 2,
                selected_lag=chosen,
                correlations=[
                    lag_correlation(d, m, chosen) for d, m in zip(differences, masks, strict=True)
                ],
            )
        )
    fixed = valid.all(axis=0) & (bits == bits[0]).all(axis=0)
    result = dict(
        input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        convention="bit=1 for positive real template deviation after independent known-pilot "
        "phase calibration and fixed +pi/4 rotation; protocol bit convention unknown",
        qualified_decisions=int(valid.sum()),
        edge_sign_agreement=float(np.mean(signs[:, 0] == signs[:, 1])),
        minimum_header_axis_real=float(np.mean(unit**2, axis=-1).real.min()),
        discovery_250_252_evaluation_253_256=score,
        all_seven_fixed_positions_per_symbol=fixed.sum(axis=-1).tolist(),
        lag_tests=tests,
        lag_partitions="Discovery XOR frames 250/251; evaluation XOR 252/253 and 254/255. "
        "Frame 256 unused. Lags in compact physical carrier order, not bytes.",
        tail_pilot_checks=[
            dict(
                frame=f + 250,
                symbol=s,
                edges=[
                    split_word(archive["deviations"][f, edge, s - 2], bins, s) for edge in range(2)
                ],
            )
            for f, s in [(0, 301), (4, 300), (4, 301), (5, 300), (5, 301)]
        ],
        limitations="Only seven frames; fixed means observed fixed, not a proven protocol "
        "constant. No FEC/CRC or field semantics. Pilot edges share the payload samples "
        "and channel/delay correction.",
    )
    (OUT / "header_structure.json").write_text(json.dumps(result, indent=2) + "\n")
    np.savez_compressed(
        OUT / "pilot_referenced_header_bits.npz",
        bits=(bits > 0).astype(np.uint8),
        valid=valid,
        bins=bins,
        frame_ids=np.arange(250, 257),
        symbols=np.arange(2, 8),
    )
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), layout="constrained")
    counts = good.sum(axis=0)
    ones = ((ordered > 0) & good).sum(axis=0)
    fractions = np.divide(
        ones, counts, out=np.full_like(ones, np.nan, dtype=float), where=counts > 0
    )
    im = axes[0].imshow(
        fractions,
        aspect="auto",
        interpolation="nearest",
        vmin=0,
        vmax=1,
        extent=(-0.5, 1003.5, 7.5, 1.5),
        cmap="coolwarm",
    )
    axes[0].set(
        xlabel="Loaded carrier index, physical frequency order",
        ylabel="OFDM symbol",
        title="Pilot-referenced header: fraction of observed signs equal to 1",
    )
    fig.colorbar(im, ax=axes[0], label="Fraction across seven frames")
    axes[1].bar(np.arange(2, 8), fixed.sum(axis=-1))
    axes[1].set(
        xlabel="OFDM symbol",
        ylabel="Positions unchanged in all seven frames",
        title="Observed constants are not yet identified protocol fields",
        ylim=(0, 1004),
    )
    fig.savefig(OUT / "header_structure.png", dpi=160)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
