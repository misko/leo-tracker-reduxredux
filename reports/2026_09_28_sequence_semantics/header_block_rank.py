"""Test a fixed 32-input linear image at every contiguous114-carrier start."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.io import loadmat

BASE = Path(__file__).parent


def rank(rows, stop=None):
    pivots = {}
    for row in rows:
        while row:
            bit = row.bit_length() - 1
            if bit not in pivots:
                pivots[bit] = row
                if stop and len(pivots) >= stop:
                    return len(pivots)
                break
            row ^= pivots[bit]
    return len(pivots)


def main():
    source = BASE / "local/header-reference-0-77.npz"
    template_path = (
        BASE.parents[1]
        / "docs/research/starlink-literature/local/data/ut-pilots"
        / "supplement/reference-template/referenceTemplate.mat"
    )
    bins = np.array(
        [k for k in range(2, 1022) if k not in range(488, 496) and k not in range(528, 536)]
    )
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = np.load(source)["symbols"][:, :, bins] * np.exp(-0.5j * np.pi * template[bins, 1:7].T)
    valid = (abs(z.imag) < 0.05) & (abs(abs(z.real) - 1) < 0.05)
    counts = dict(
        starts=0,
        discovery_quality=0,
        variable_support=0,
        rank_at_most32=0,
        evaluation_quality=0,
        combined_rank_at_most32=0,
    )
    rows = []
    width = 114
    split = 39
    mask = (1 << width) - 1
    for name, order in [
        ("fft", np.argsort(bins)),
        ("physical", np.argsort(np.fft.fftfreq(1024)[bins])),
    ]:
        for direction in (1, -1):
            ids = order[::direction]
            bits = (z[:, :, ids].real >= 0).reshape(78, -1)
            quality = valid[:, :, ids].reshape(78, -1)
            n = bits.shape[1]
            packed = [
                int.from_bytes(np.packbits(b, bitorder="little").tobytes(), "little") for b in bits
            ]
            differences = [b ^ packed[0] for b in packed]
            bad = np.r_[0, np.cumsum(~quality[:split].all(axis=0))]
            eval_bad = np.r_[0, np.cumsum(~quality[split:].all(axis=0))]
            for start in range(n - width + 1):
                counts["starts"] += 1
                if bad[start + width] != bad[start]:
                    continue
                counts["discovery_quality"] += 1
                train = [(b >> start) & mask for b in differences[1:split]]
                active = 0
                for b in train:
                    active |= b
                if active.bit_count() < 64:
                    continue
                counts["variable_support"] += 1
                discovery_rank = rank(train, stop=33)
                if discovery_rank > 32:
                    continue
                counts["rank_at_most32"] += 1
                evaluation_good = eval_bad[start + width] == eval_bad[start]
                combined = None
                distinct_words = None
                nonmodal_frames = None
                if evaluation_good:
                    counts["evaluation_quality"] += 1
                    combined = rank([(b >> start) & mask for b in differences[1:]])
                    counts["combined_rank_at_most32"] += combined <= 32
                    words = [(b >> start) & mask for b in packed]
                    histogram = Counter(words)
                    distinct_words = len(histogram)
                    nonmodal_frames = len(words) - max(histogram.values())
                rows.append(
                    dict(
                        order=name,
                        direction=direction,
                        start=start,
                        discovery_active_columns=active.bit_count(),
                        discovery_rank=discovery_rank,
                        evaluation_quality=bool(evaluation_good),
                        combined_rank=combined,
                        distinct_words=distinct_words,
                        nonmodal_frames=nonmodal_frames,
                    )
                )
    result = dict(
        counts=counts,
        rows=rows,
        discovery_frames=[0, 38],
        evaluation_frames=[39, 77],
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, template_path)
        },
        limitation="Necessary condition for fixed affine encoding with at most32 variable "
        "inputs, not sufficient evidence of a code. Fixed mask canceled by frame XOR. "
        "Exact rank sensitive to errors. Requires64 changing discovery columns and "
        "all-frame hard-axis quality. Other layouts, masks, or encoder state not excluded.",
    )
    (BASE / "local/header_block_rank.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
