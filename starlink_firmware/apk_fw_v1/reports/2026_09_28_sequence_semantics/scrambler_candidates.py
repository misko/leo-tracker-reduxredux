"""Compare template-derived and patent-tap second-plane hypotheses on direct parity."""

import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
from odd_parity_probe import check_score, lane_order, walsh, windows
from phase_lfsr import extend

BASE = Path(__file__).resolve().parent


def tap_shift(sequence, advance):
    """For c=b XOR shifted(b), rotation -2b-c has high bit b XOR c."""
    c = sequence ^ np.roll(sequence, -advance)
    doubled = np.r_[sequence, sequence[:14]]
    candidates = np.lib.stride_tricks.sliding_window_view(doubled, 15)
    matches = np.flatnonzero((candidates == c[:15]).all(axis=1))
    if len(matches) != 1:
        raise ValueError("Expected a unique nonzero maximal-sequence phase")
    return int((advance - matches[0]) % len(sequence))


def main():
    path = BASE / "local/rotational_header_bits.npz"
    modelpath = BASE / "local/rotational_descramble.json"
    p = np.load(path)
    seed = json.loads(modelpath.read_text())["seed"]
    seq = extend(seed, 32782)[:32767]
    physical = np.array([k for k in np.argsort(np.fft.fftfreq(1024)) if 2 <= k < 1022])
    ix = np.array([physical.tolist().index(k) for k in p["bins"]])
    pos = np.arange(6)[:, None] * 1020 + ix[None] - 40
    masks = np.array([m for m in range(1, 16384) if m & 127 and m >> 7])
    results = []
    for shift in [16383, tap_shift(seq, 8), tap_shift(seq, -8)]:
        bits = p["bits"] ^ seq[(pos + 16383) % 32767] ^ seq[(pos + shift) % 32767]
        best = None
        for name, order in [("physical", np.arange(1004)), ("fft", np.argsort(p["bins"]))]:
            for direction, lanes, blocked in itertools.product(
                [1, -1], [1, 4, 8, 16, 32], [False, True]
            ):
                indices = order[::direction][lane_order(1004, lanes)]
                x, good = bits[:, :, indices], p["valid"][:, :, indices]
                for phase, streams in itertools.product(
                    range(3), itertools.combinations(range(3), 2)
                ):
                    w = [windows(x[f], phase, streams, blocked) for f in range(7)]
                    q = [windows(good[f], phase, streams, blocked).all(axis=1) for f in range(7)]
                    w = [a[b] for a, b in zip(w, q, strict=True)]
                    packed = w[0].astype(np.int64) @ (1 << np.arange(14))
                    correlations = walsh(np.bincount(packed, minlength=16384)) / len(packed)
                    mask = int(masks[np.argmax(abs(correlations[masks]))])
                    score = float(correlations[mask])
                    if best is None or abs(score) > abs(best["discovery"]):
                        best = dict(
                            order=name,
                            direction=direction,
                            lanes=lanes,
                            blocked=blocked,
                            phase=phase,
                            streams=streams,
                            mask=mask,
                            discovery=score,
                            per_frame=[check_score(a, mask) for a in w],
                            counts=list(map(len, w)),
                        )
        results.append(dict(second_plane_shift=shift, layouts=360, selected=best))
    output = dict(
        results=results,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [path, modelpath]
        },
        source="https://patents.google.com/patent/US12074683B1/en",
        limitations="Figure 9 interpreted with both tap-advance signs; implementation "
        "not verified. Direct all-weight parity on OFDM 2..7, first frame discovery, "
        "remaining six evaluation. Same fixed masks cancel in prior frame-XOR tests.",
    )
    (BASE / "local/scrambler_candidates.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
