"""Search exact seven-tap convolutional relations without chosen generators."""

import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from short_header_parity import check_score, pair_windows

BASE = Path(__file__).parent


def mixed_null_check(windows):
    """Return a nontrivial homogeneous check using variable columns in both streams."""
    active = (windows.mean(axis=0) >= 0.1) & (windows.mean(axis=0) <= 0.9)
    rows = list(map(int, windows.astype(np.int64) @ (1 << np.arange(14))))
    rows.extend(1 << j for j in range(14) if not active[j])
    pivots = {}
    for row in rows:
        while row:
            bit = row.bit_length() - 1
            if bit not in pivots:
                pivots[bit] = row
                break
            row ^= pivots[bit]
    basis = []
    for free in range(14):
        if free in pivots:
            continue
        mask = 1 << free
        for bit, row in sorted(pivots.items()):
            if (row & mask).bit_count() % 2:
                mask |= 1 << bit
        basis.append(mask)
    # If no basis vector mixes streams, a pair of opposite-stream vectors does.
    candidates = basis + [a ^ b for a, b in itertools.combinations(basis, 2)]
    candidates = [m for m in candidates if m & 127 and m >> 7]
    return min(candidates, key=lambda m: (m.bit_count(), m)) if candidates else None


def main():
    paths = [
        BASE / "local/pilot_referenced_header_bits.npz",
        BASE / "local/full-reference-0-12.npz",
    ]
    old, new = [np.load(p) for p in paths]
    bins = old["bins"]
    template_path = (
        BASE.parents[1]
        / "docs/research/starlink-literature/local/data/ut-pilots"
        / "supplement/reference-template/referenceTemplate.mat"
    )
    template = np.exp(0.5j * np.pi * loadmat(template_path)["referenceTemplateRotations"])
    z = new["symbols"][:, 1:7][:, :, bins] * template[bins, 1:7].T.conj()
    bits = [old["bits"], (z.real >= 0).astype(np.uint8)]
    valid = [old["valid"], (abs(z.imag) < 0.05) & (abs(abs(z.real) - 1) < 0.05)]
    candidates = []
    tested = 0
    for order_name, order in [
        ("physical", np.argsort(np.fft.fftfreq(1024)[bins])),
        ("fft", np.argsort(bins)),
    ]:
        for direction, symbol in itertools.product([1, -1], range(6)):
            ids = order[::direction]
            datasets = []
            for b, v in zip(bits, valid, strict=True):
                count = len(b) // 2 * 2
                b, v = b[:count, symbol][:, ids], v[:count, symbol][:, ids]
                datasets.append((b[::2] ^ b[1::2], v[::2] & v[1::2]))
            discovery, quality = datasets[0]
            for start in range(len(ids) - 113):
                words = discovery[:, start : start + 114]
                if not quality[:, start : start + 114].all() or not 0.1 <= words.mean() <= 0.9:
                    continue
                for pair in itertools.combinations(range(3), 2):
                    w = pair_windows(words, 0, pair)
                    tested += 1
                    mask = mixed_null_check(w)
                    if mask is None:
                        continue
                    evaluation, q = datasets[1]
                    e = pair_windows(evaluation[:, start : start + 114], 0, pair)
                    candidates.append(
                        dict(
                            order=order_name,
                            direction=direction,
                            symbol=symbol + 2,
                            start=start,
                            first_bin=int(bins[ids[start]]),
                            pair=pair,
                            mask=mask,
                            discovery=check_score(w, mask),
                            evaluation=check_score(e, mask),
                            evaluation_qualified=bool(q[:, start : start + 114].all()),
                        )
                    )
    result = dict(
        tested=tested,
        exact_discovery_candidates=candidates,
        exact_evaluation=sum(
            c["evaluation"] == 1 and c["evaluation_qualified"] for c in candidates
        ),
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths + [template_path]
        },
        scope="114-bit within-symbol direct serialization; all starts, two carrier orders "
        "and directions, each pair of three streams, all homogeneous seven-tap checks "
        "on variable columns. Fixed masks cancel by frame XOR. Exact checks only; "
        "noise, interleaving, variable masks and low-activity regions remain limitations. "
        "Discovery/evaluation reuse prior UT frames from the same recording.",
    )
    (BASE / "local/blind_header_114.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "input_sha256"}, indent=2))


if __name__ == "__main__":
    main()
