"""Held-out search for short parity checks in a direct rate-1/3 serialization.

This is a restricted model probe, not a header decoder. XOR between frames
cancels fixed carrier templates. Even-weight checks ignore global sign flips.
"""

import hashlib
import itertools
import json
from pathlib import Path

import numpy as np


def walsh(values):
    out = np.asarray(values, dtype=float).copy()
    width = 1
    while width < len(out):
        blocks = out.reshape(-1, width * 2)
        a, b = blocks[:, :width].copy(), blocks[:, width:].copy()
        blocks[:, :width], blocks[:, width:] = a + b, a - b
        width *= 2
    return out


def pair_windows(rows, phase, pair):
    chunks = []
    for row in rows:
        triples = row[phase : phase + (len(row) - phase) // 3 * 3].reshape(-1, 3)
        if len(triples) < 7:
            continue
        windows = np.lib.stride_tricks.sliding_window_view(triples[:, pair], 7, axis=0)
        chunks.append(windows.reshape(-1, 14))
    return np.concatenate(chunks).astype(np.uint8)


def best_check(windows):
    packed = windows.astype(np.int64) @ (1 << np.arange(14))
    correlation = walsh(np.bincount(packed, minlength=1 << 14)) / len(packed)
    # Each of two streams must contribute; discard odd checks to cancel row sign ambiguity.
    masks = np.array(
        [m for m in range(1, 1 << 14) if m & 127 and m >> 7 and m.bit_count() % 2 == 0]
    )
    mask = int(masks[np.argmax(abs(correlation[masks]))])
    return mask, float(correlation[mask])


def check_score(windows, mask):
    bits = (mask >> np.arange(14)) & 1
    return float(np.mean(1 - 2 * ((windows.astype(int) @ bits) % 2)))


def main():
    root = Path(__file__).resolve().parents[2]
    source = root / "reports/2026_09_27_ut_header/local/fullband/soft_deviations.npz"
    data = np.load(source)
    bins = data["subcarriers"]
    # Exclude symbols 2/4, whose static regions could create trivial parity checks.
    symbols = np.array([3, 5, 6, 7])
    bits = (data["deviations"][:, symbols - 2].real > 0).astype(np.uint8)
    trials = []
    for order_name, order in (
        ("physical_frequency", np.argsort(np.fft.fftfreq(1024)[bins])),
        ("native_fft_index", np.arange(len(bins))),
    ):
        for direction in (1, -1):
            ordered = bits[:, :, order[::direction]]
            discovery = ordered[0] ^ ordered[1]
            validation = ordered[2] ^ ordered[3]
            final = ordered[4] ^ ordered[5]
            for phase, pair in itertools.product(range(3), itertools.combinations(range(3), 2)):
                a = pair_windows(discovery, phase, pair)
                mask, score = best_check(a)
                trials.append(
                    dict(
                        order=order_name,
                        direction=direction,
                        phase=phase,
                        pair=list(pair),
                        mask=mask,
                        discovery_score=score,
                        validation_score=check_score(pair_windows(validation, phase, pair), mask),
                        final_score=check_score(pair_windows(final, phase, pair), mask),
                        windows=len(a),
                    )
                )
    # Selection uses only discovery; validation and final are never used to choose the mask.
    selected = max(trials, key=lambda r: abs(r["discovery_score"]))
    result = dict(
        input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        scope="Direct frequency serialization, two of three output streams, seven taps, "
        "within-symbol windows, fixed even parity checks; no interleaver/descrambler search.",
        symbols=symbols.tolist(),
        discovery_frames=[250, 251],
        validation_frames=[252, 253],
        final_frames=[254, 255],
        selected=selected,
        trials=trials,
        limitation="Noise, unknown interleaving, puncturing, variable boundaries, or "
        "frame-dependent scrambling can hide a real code. A negative result only "
        "fails to support this restricted model; it does not exclude convolutional coding.",
    )
    out = Path(__file__).parent / "local/header-code-probe.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(selected, indent=2))


if __name__ == "__main__":
    main()
