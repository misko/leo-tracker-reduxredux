"""Test odd-weight parity relations now that pilot-referenced polarity is available."""

import hashlib
import itertools
import json
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str((BASE.parents[3] / "reports") / "2026_09_28_ds7_ds8_correspondence"))
sys.path.insert(0, str((BASE.parents[3] / "reports") / "2026_09_27_ds7_header"))
from header_code_probe import check_score, walsh  # noqa: E402
from header_layout_probe import lane_order, windows  # noqa: E402


def best_odd_check(w):
    if len(w) < 50:
        return None
    packed = w.astype(np.int64) @ (1 << np.arange(14))
    scores = walsh(np.bincount(packed, minlength=1 << 14)) / len(packed)
    masks = np.array(
        [m for m in range(1, 1 << 14) if m & 127 and m >> 7 and m.bit_count() % 2 == 1]
    )
    mask = int(masks[np.argmax(abs(scores[masks]))])
    return mask, float(scores[mask])


def main():
    source = BASE / "local/pilot_referenced_header_bits.npz"
    archive = np.load(source)
    selected_symbols = [1, 3, 4, 5]  # OFDM 3,5,6,7; exclude mostly fixed 2/4
    bits = archive["bits"][:, selected_symbols]
    valid = archive["valid"][:, selected_symbols]
    bins = archive["bins"]
    trials = []
    for order_name, order in [
        ("physical", np.argsort(np.fft.fftfreq(1024)[bins])),
        ("fft", np.arange(len(bins))),
    ]:
        for direction, lanes, blocked in itertools.product(
            [1, -1], [1, 4, 8, 16, 32], [False, True]
        ):
            indices = order[::direction][lane_order(len(bins), lanes)]
            ordered = bits[:, :, indices]
            qualified = valid[:, :, indices]
            pairs = [ordered[a] ^ ordered[a + 1] for a in [0, 2, 4]]
            supports = [qualified[a] & qualified[a + 1] for a in [0, 2, 4]]
            for phase, streams in itertools.product(range(3), itertools.combinations(range(3), 2)):
                w = [windows(p, phase, streams, blocked) for p in pairs]
                support = [windows(v, phase, streams, blocked).all(axis=1) for v in supports]
                w = [a[b] for a, b in zip(w, support, strict=True)]
                if min(map(len, w)) < 50:
                    continue
                mask, score = best_odd_check(w[0])
                trials.append(
                    dict(
                        order=order_name,
                        direction=direction,
                        lanes=lanes,
                        blocked=blocked,
                        phase=phase,
                        streams=streams,
                        mask=mask,
                        weight=mask.bit_count(),
                        discovery=score,
                        evaluation=check_score(w[1], mask),
                        final=check_score(w[2], mask),
                        counts=list(map(len, w)),
                    )
                )
    selected = max(trials, key=lambda row: abs(row["discovery"]))
    result = dict(
        input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        selected_by_discovery=selected,
        trials=trials,
        scope="Odd-weight two-stream seven-tap parity checks; 360 layouts, "
        "discovery XOR frames 250/251, evaluation XOR 252/253 and 254/255. "
        "Only windows with all 14 decisions qualified in both frames. "
        "Frame XOR cancels a fixed carrier mask; pilot reference removes "
        "the prior per-symbol sign ambiguity that prevented odd checks.",
        limitations="Exploratory reuse; static regions can inflate parity scores. "
        "No arbitrary interleaver or general LDPC identification; no payload decode.",
    )
    (BASE / "local/odd_parity_probe.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(selected=selected, trials=len(trials)), indent=2))


if __name__ == "__main__":
    main()
