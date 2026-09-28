"""Audit every cached full-band UT data symbol without resolving its polarity.

Input: analyze.py's soft_deviations.npz, seven frames 250..256.
Outputs are local research products, not decoded protocol fields.
"""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from phase_model import codebook

SEED = "010010100010010010001000000000001000100000101000001010100010"


def split_word(z, bins, symbol):
    """Fit each physical band independently; never fit against the codebook."""
    physical = np.array(
        [k for k in range(2, 1022) if k not in range(488, 496) and k not in range(528, 536)]
    )
    physical = physical[np.argsort(np.fft.fftfreq(1024)[physical])]
    lookup = {int(k): i for i, k in enumerate(physical)}
    compact = np.array([lookup[int(k)] for k in bins])
    mapping = (compact - 16 * symbol) % 60
    words, scores = [], []
    for mask in [compact < 502, compact >= 502]:
        counts = np.bincount(mapping[mask], minlength=60)
        if not counts.all():
            return None
        sums = np.bincount(mapping[mask], weights=z[mask].real, minlength=60)
        signs = np.where(sums >= 0, 1, -1)
        words.append("".join("1" if x > 0 else "0" for x in signs))
        scores.append(
            float(
                np.mean(z[mask].real * signs[mapping[mask]]) / np.sqrt(np.mean(abs(z[mask]) ** 2))
            )
        )
    book = codebook([int(x) for x in SEED])
    candidates = [
        dict(phase_index=k, polarity=p)
        for k, w in enumerate(book)
        for p, candidate in [(1, w), (-1, w.translate(str.maketrans("01", "10")))]
        if words[0] == words[1] == candidate
    ]
    return dict(
        words=words,
        scores=scores,
        exact_band_agreement=words[0] == words[1],
        generator_candidates=candidates,
    )


def relative_bits(z, bins):
    """Adjacent physical carrier products cancel independent symbol polarity."""
    pairs = np.flatnonzero(np.diff(bins) == 1)
    signs = np.where(z.real >= 0, 1, -1)
    return signs[..., pairs] * signs[..., pairs + 1], pairs


def stability(bits, valid, split=3):
    """Select positions unanimous on discovery frames; evaluate later frames."""
    selected = valid[:split].all(axis=0) & (abs(bits[:split].sum(axis=0)) == split)
    expected = bits[0]
    held = valid[split:] & selected
    return {
        "selected_positions": int(selected.sum()),
        "evaluation_decisions": int(held.sum()),
        "evaluation_correct": int(((bits[split:] == expected) & held).sum()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    archive = np.load(args.input)
    z, bins = archive["deviations"], archive["subcarriers"]
    if z.shape[:2] != (7, 300):
        raise ValueError("Expected the seven complete UT frames 250..256")
    unit = z / np.maximum(abs(z), 1e-12)
    coherence = abs(np.mean(unit**2, axis=-1))
    bits, pairs = relative_bits(z, bins)
    # A sign decision is qualified only near the fitted real axis. These are
    # soft-symbol quality flags, not independent receiver confirmation or BER.
    quality = (abs(unit.real) > 0.9) & np.isfinite(z)
    valid = quality[..., pairs] & quality[..., pairs + 1]
    valid &= coherence[..., None] > 0.9
    header = stability(bits[:, :6], valid[:, :6])  # OFDM 2..7, common early range
    controls = []
    for shift in [7, 19, 43, 101]:
        wrong = bits[:, :6].copy()
        wrong[3:] = np.roll(wrong[3:], shift, axis=-1)
        controls.append(dict(shift=shift, **stability(wrong, valid[:, :6])))
    # Save relative decisions only where both carriers pass. No arbitrary
    # per-symbol absolute polarity is exported as a decoded payload bit.
    np.savez_compressed(
        args.out / "relative_header_bits.npz",
        bits=bits[:, :6],
        valid=valid[:, :6],
        carrier_pairs=np.stack([bins[pairs], bins[pairs + 1]], axis=-1),
        frame_ids=np.arange(250, 257),
        symbols=np.arange(2, 8),
    )
    result = {
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "frames": list(range(250, 257)),
        "symbols_examined": int(coherence.size),
        "carriers": len(bins),
        "axis_coherence_threshold": 0.9,
        "binary_symbols_by_frame": [
            list((np.flatnonzero(row > 0.9) + 2).astype(int).tolist()) for row in coherence
        ],
        "qualified_relative_header_decisions": int(valid[:, :6].sum()),
        "header_discovery_250_252_evaluation_253_256": header,
        "shifted_evaluation_controls": controls,
        "binary_symbol_split_band_fits": [
            dict(frame=int(250 + f), symbol=int(s + 2), **split_word(z[f, s], bins, s + 2))
            for f, s in zip(*np.where(coherence > 0.9), strict=True)
        ],
        "limitation": "Exploratory reuse of seven previously inspected frames; adjacent pairs "
        "overlap, and template/calibration are shared. Relative signs are not FEC/CRC-verified "
        "bits or independent information bits. Per-symbol absolute polarity remains unknown.",
    }
    (args.out / "rest_signal.json").write_text(json.dumps(result, indent=2) + "\n")
    fig, axes = plt.subplots(2, 1, figsize=(12, 6), layout="constrained")
    for f, row in enumerate(coherence):
        axes[0].plot(np.arange(2, 302), row, alpha=0.65, label=str(250 + f))
        axes[1].plot(np.arange(2, 22), row[:20], marker=".", label=str(250 + f))
    for ax in axes:
        ax.axhline(0.9, color="black", linestyle="--", linewidth=0.8)
        ax.set(xlabel="OFDM symbol", ylabel="Binary-axis coherence", ylim=(0, 1.04))
    axes[0].set_title("Full-band UT: all 300 saved data symbols in seven frames")
    axes[1].set_title("Early-symbol detail; a binary axis does not resolve bit polarity")
    axes[1].legend(title="UT frame", ncol=7, fontsize=8)
    fig.savefig(args.out / "rest_signal.png", dpi=160)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
