"""Search arbitrary within-symbol starts for an explicitly assumed rate-1/3 code."""

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent


def syndromes(words, generators):
    triples = words.reshape(*words.shape[:-1], -1, 3)
    w = np.lib.stride_tricks.sliding_window_view(triples, 7, axis=-2)
    taps = (np.asarray(generators)[:, None] >> np.arange(6, -1, -1)) & 1
    checks = []
    for a, b in itertools.combinations(range(3), 2):
        checks.append(((w[..., a, :] @ taps[b]) ^ (w[..., b, :] @ taps[a])) & 1)
    return np.stack(checks, axis=-1)


def main(lengths=(69, 81, 87, 99), output=None):
    if any(length < 21 or length % 3 for length in lengths):
        raise ValueError("Lengths must be multiples of three and at least 21")
    paths = [
        BASE / "local/pilot_referenced_header_bits.npz",
        BASE / "local/full-reference-0-12.npz",
    ]
    old, new = [np.load(p) for p in paths]
    bins = old["bins"]
    tp = (
        BASE.parents[3]
        / "docs/research/starlink-literature/local/data/ut-pilots"
        / "supplement/reference-template/referenceTemplate.mat"
    )
    template = np.exp(0.5j * np.pi * loadmat(tp)["referenceTemplateRotations"])
    z = new["symbols"][:, 1:7][:, :, bins] * template[bins, 1:7].T.conj()
    bits = [old["bits"], (z.real >= 0).astype(np.uint8)]
    valid = [old["valid"], (abs(z.imag) < 0.05) & (abs(abs(z.real) - 1) < 0.05)]
    groups = []
    total = 0
    for name, order in [
        ("physical", np.argsort(np.fft.fftfreq(1024)[bins])),
        ("fft", np.argsort(bins)),
    ]:
        for direction, symbol, length in itertools.product([1, -1], range(6), lengths):
            ids = order[::direction]
            datasets = []
            for b, v in zip(bits, valid, strict=True):
                count = len(b) // 2 * 2
                b = b[:count, symbol][:, ids]
                v = v[:count, symbol][:, ids]
                d = b[::2] ^ b[1::2]
                q = v[::2] & v[1::2]
                words = np.lib.stride_tricks.sliding_window_view(d, length, axis=-1)
                good = np.lib.stride_tricks.sliding_window_view(q, length, axis=-1).all(axis=(0, 2))
                activity = words.mean(axis=(0, 2))
                datasets.append((words, good, activity))
            w, good, activity = datasets[0]
            eligible = good & (activity >= 0.1) & (activity <= 0.9)
            starts = np.flatnonzero(eligible)
            if not len(starts):
                continue
            for generators in itertools.permutations([0o133, 0o171, 0o165]):
                score = syndromes(w[:, starts], generators).mean(axis=(0, 2, 3))
                total += len(starts)
                chosen = int(starts[np.argmin(score)])
                other, q, act = datasets[1]
                evaluation = syndromes(other[:, chosen], generators)
                groups.append(
                    dict(
                        order=name,
                        direction=direction,
                        symbol=symbol + 2,
                        length=length,
                        start=chosen,
                        first_bin=int(bins[ids[chosen]]),
                        first_column=int(ids[chosen]),
                        generators=[oct(x) for x in generators],
                        discovery_error=float(score.min()),
                        evaluation_error=float(evaluation.mean()),
                        evaluation_qualified=bool(q[chosen]),
                        activity=[float(activity[chosen]), float(act[chosen])],
                        exact_discovery=int((score == 0).sum()),
                    )
                )
    best = min(groups, key=lambda r: r["discovery_error"])
    result = dict(
        selected_by_discovery=best,
        starts_tested=total,
        groups=groups,
        exact_discovery=sum(g["exact_discovery"] for g in groups),
        input_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths + [tp]},
        scope="Assumed octal 133/171/165 code only; all six stream permutations, "
        "direct serialization and arbitrary within-symbol offsets. Fixed masks "
        "cancel by frame XOR. No interleaver search. Reused data; checks dependent.",
    )
    destination = output or BASE / "local/moving_header_code.json"
    Path(destination).write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ["groups", "input_sha256"]}, indent=2
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lengths", type=int, nargs="+", default=[69, 81, 87, 99])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    main(args.lengths, args.output)
