"""Probe short frequency-prefix convolutional headers; no semantic decoding."""

import hashlib
import itertools
import json
import sys
from pathlib import Path

import numpy as np
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str((BASE.parents[3] / "reports") / "2026_09_27_ds7_header"))
from header_code_probe import check_score, pair_windows, walsh  # noqa: E402


def best_variable_check(w):
    """Avoid parity checks that use a nearly constant input column."""
    active = (w.mean(axis=0) >= 0.1) & (w.mean(axis=0) <= 0.9)
    allowed = int(active.astype(np.int64) @ (1 << np.arange(14)))
    masks = np.array([m for m in range(1, 16384) if m & 127 and m >> 7 and not m & ~allowed])
    if not len(masks):
        return None
    packed = w.astype(np.int64) @ (1 << np.arange(14))
    scores = walsh(np.bincount(packed, minlength=16384)) / len(w)
    mask = int(masks[np.argmax(abs(scores[masks]))])
    return mask, float(scores[mask])


def main():
    paths = [
        BASE / "local/pilot_referenced_header_bits.npz",
        BASE / "local/full-reference-0-12.npz",
    ]
    old, new = [np.load(p) for p in paths]
    bins = old["bins"]
    tpath = (
        BASE.parents[3]
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement"
        / "reference-template/referenceTemplate.mat"
    )
    template = np.exp(0.5j * np.pi * loadmat(tpath)["referenceTemplateRotations"])
    z = new["symbols"][:, 1:7][:, :, bins] * template[bins, 1:7].T.conj()
    bits = [old["bits"], (z.real >= 0).astype(np.uint8)]
    valid = [old["valid"], (abs(z.imag) < 0.05) & (abs(abs(z.real) - 1) < 0.05)]
    trials = []
    for ordername, order in [
        ("physical", np.argsort(np.fft.fftfreq(1024)[bins])),
        ("fft", np.argsort(bins)),
    ]:
        for direction, symbol, length in itertools.product([1, -1], range(6), [69, 81, 87, 99]):
            ids = order[::direction][:length]
            pairs, supports = [], []
            for b, v in zip(bits, valid, strict=True):
                count = len(b) // 2 * 2
                a = b[:count, symbol][:, ids]
                q = v[:count, symbol][:, ids]
                pairs.append(a[::2] ^ a[1::2])
                supports.append(q[::2] & q[1::2])
            for phase, streams in itertools.product(range(3), itertools.combinations(range(3), 2)):
                w = [pair_windows(p, phase, streams) for p in pairs]
                q = [pair_windows(p, phase, streams).all(axis=1) for p in supports]
                w = [a[b] for a, b in zip(w, q, strict=True)]
                if min(map(len, w)) < 30:
                    continue
                candidate = best_variable_check(w[0])
                if candidate is None:
                    continue
                mask, score = candidate
                trials.append(
                    dict(
                        order=ordername,
                        direction=direction,
                        symbol=symbol + 2,
                        length=length,
                        phase=phase,
                        streams=streams,
                        mask=mask,
                        discovery=score,
                        evaluation=check_score(w[1], mask),
                        windows=list(map(len, w)),
                    )
                )
    selected = max(trials, key=lambda x: abs(x["discovery"]))
    result = dict(
        input_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths + [tpath]},
        selected_by_discovery=selected,
        trials=trials,
        exact_discovery=sum(abs(t["discovery"]) == 1 for t in trials),
        exact_both=sum(
            abs(t["discovery"]) == 1 and t["evaluation"] == t["discovery"] for t in trials
        ),
        limitations="Exploratory reuse of 20 UT frames, same recording. Short prefixes only; "
        "no arbitrary interleaver. Overlapping windows are not independent. "
        "Constant-column exclusion may omit real low-entropy headers. No inferred fields.",
    )
    (BASE / "local/short_header_parity.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ["input_sha256", "trials"]}, indent=2
        )
    )
    print("trials", len(trials))


if __name__ == "__main__":
    main()
