"""Test 114-bit rectangular time/frequency blocks against a 32-input bound."""

import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
from header_block_rank import rank
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent


def packed_rows(bits):
    return [int.from_bytes(np.packbits(row, bitorder="little").tobytes(), "little") for row in bits]


def block(data, symbols, start, width):
    return data[:, list(symbols), start : start + width].reshape(len(data), -1)


def main():
    source = BASE / "local/header-reference-0-77.npz"
    template_path = (
        BASE.parents[3]
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement"
        / "reference-template/referenceTemplate.mat"
    )
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = np.load(source)["symbols"] * np.exp(-0.5j * np.pi * template[:, 1:7].T)
    bits = z.real >= 0
    quality = (abs(z.imag) < 0.05) & (abs(abs(z.real) - 1) < 0.05)
    allowed = set(
        k for k in range(2, 1022) if k not in range(488, 496) and k not in range(528, 536)
    )
    rows, summaries = [], []
    for height in (2, 3, 6):
        width = 114 // height
        counts = dict(
            height=height,
            width=width,
            starts=0,
            discovery_quality=0,
            variable_support=0,
            discovery_low_rank=0,
            evaluation_quality=0,
            combined_low_rank=0,
        )
        for symbols in itertools.combinations(range(6), height):
            for start in range(2, 1022 - width + 1):
                if not set(range(start, start + width)).issubset(allowed):
                    continue
                counts["starts"] += 1
                valid = block(quality, symbols, start, width)
                if not valid[:39].all():
                    continue
                counts["discovery_quality"] += 1
                values = block(bits, symbols, start, width)
                differences = values ^ values[0]
                active = int(differences[:39].any(axis=0).sum())
                if active < 64:
                    continue
                counts["variable_support"] += 1
                train_rank = rank(packed_rows(differences[1:39]), stop=33)
                if train_rank > 32:
                    continue
                counts["discovery_low_rank"] += 1
                combined = None
                symbol_ranks = None
                if valid[39:].all():
                    counts["evaluation_quality"] += 1
                    combined = rank(packed_rows(differences[1:]))
                    counts["combined_low_rank"] += combined <= 32
                    if combined <= 32:
                        symbol_ranks = [
                            rank(
                                packed_rows(
                                    bits[:, s, start : start + width]
                                    ^ bits[0, s, start : start + width]
                                )
                            )
                            for s in symbols
                        ]
                rows.append(
                    dict(
                        symbols=[s + 2 for s in symbols],
                        start_bin=start,
                        width=width,
                        discovery_rank=train_rank,
                        combined_rank=combined,
                        active_columns=active,
                        per_symbol_ranks=symbol_ranks,
                    )
                )
        summaries.append(counts)
    output = dict(
        summaries=summaries,
        rows=rows,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, template_path)
        },
        limitation="Necessary fixed-affine32input condition only. Complete contiguous "
        "native-bin rectangles exclude pilots/gutters; all symbol subsets within2..7. "
        "Rank invariant to within-block permutations; cross-block interleavers, "
        "variable masks/states and decision errors are not addressed.",
    )
    (BASE / "local/header_rectangle_rank.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
