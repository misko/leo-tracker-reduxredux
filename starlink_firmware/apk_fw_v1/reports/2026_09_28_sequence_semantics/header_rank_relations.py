"""Separate copied columns from higher-order discovery parity relations."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent


def dependencies(columns):
    pivots, relations = {}, []
    for index, value in enumerate(columns):
        combination = 1 << index
        while value:
            bit = value.bit_length() - 1
            if bit not in pivots:
                pivots[bit] = (value, combination)
                break
            prior, mask = pivots[bit]
            value ^= prior
            combination ^= mask
        if not value:
            relations.append(combination)
    return relations


def column_words(bits):
    return [int.from_bytes(np.packbits(c, bitorder="little").tobytes(), "little") for c in bits.T]


def audit(bits):
    differences = bits ^ bits[0]
    train = column_words(differences[:39])
    held = column_words(differences[39:])
    relations = dependencies(train)
    # Counts of unique changing columns after fixed-mask cancellation measure
    # whether rank reduction extends beyond constant/copy/complement positions.
    unique_train = len(set(train) - {0})
    full = column_words(differences)
    unique_full = len(set(full) - {0})
    rows = []
    for mask in relations:
        positions = [i for i in range(bits.shape[1]) if mask >> i & 1]
        syndrome = 0
        for i in positions:
            syndrome ^= held[i]
        rows.append(
            dict(positions=positions, weight=len(positions), evaluation_errors=syndrome.bit_count())
        )
    return dict(
        unique_discovery_columns=unique_train, unique_combined_columns=unique_full, relations=rows
    )


def main():
    rank_path = BASE / "local/header_block_rank.json"
    prior = json.loads(rank_path.read_text())
    for name, digest in prior["input_sha256"].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest
    source = BASE / "local/header-reference-0-77.npz"
    template_path = (
        BASE.parents[3]
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement"
        / "reference-template/referenceTemplate.mat"
    )
    bins = np.array(
        [k for k in range(2, 1022) if k not in range(488, 496) and k not in range(528, 536)]
    )
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = np.load(source)["symbols"][:, :, bins] * np.exp(-0.5j * np.pi * template[bins, 1:7].T)
    layouts, coordinates = {}, {}
    for name, ids in [
        ("fft", np.argsort(bins)),
        ("physical", np.argsort(np.fft.fftfreq(1024)[bins])),
    ]:
        for direction in (1, -1):
            layouts[name, direction] = (z[:, :, ids[::direction]].real >= 0).reshape(78, -1)
            coordinates[name, direction] = [
                (s, int(b)) for s in range(6) for b in bins[ids[::direction]]
            ]
    rows = []
    for item in prior["rows"]:
        if not item["evaluation_quality"]:
            continue
        start = item["start"]
        result = audit(layouts[item["order"], item["direction"]][:, start : start + 114])
        higher = [r for r in result["relations"] if r["weight"] >= 3]
        rows.append(
            dict(
                **item,
                **result,
                higher_relations=len(higher),
                exact_higher_relations=sum(r["evaluation_errors"] == 0 for r in higher),
            )
        )
    survivors = [r for r in rows if r["combined_rank"] <= 32]
    summary = dict(
        windows=len(rows),
        combined_rank_survivors=len(survivors),
        survivors_explained_by_copies=sum(
            r["unique_combined_columns"] == r["combined_rank"] for r in survivors
        ),
        windows_with_exact_higher_relation=sum(r["exact_higher_relations"] > 0 for r in rows),
        higher_relations=sum(r["higher_relations"] for r in rows),
        exact_higher_relations=sum(r["exact_higher_relations"] for r in rows),
    )
    unique = {}
    for row in rows:
        layout = (row["order"], row["direction"])
        for relation in row["relations"]:
            if relation["weight"] < 3 or relation["evaluation_errors"]:
                continue
            indices = [row["start"] + i for i in relation["positions"]]
            key = tuple(sorted(coordinates[layout][i] for i in indices))
            parity = int(np.bitwise_xor.reduce(layouts[layout][0, indices]))
            assert key not in unique or unique[key] == parity
            unique[key] = parity
    raw_path = BASE / "local/pilot_referenced_header_bits.npz"
    raw = np.load(raw_path)
    raw_bins = {int(b): i for i, b in enumerate(raw["bins"])}
    transfers = []
    for key, parity in unique.items():
        symbols = [s for s, b in key]
        carriers = [raw_bins[b] for s, b in key]
        valid = raw["valid"][:, symbols, carriers].all(axis=1)
        observed = np.bitwise_xor.reduce(raw["bits"][:, symbols, carriers], axis=1)
        values = raw["bits"][:, symbols, carriers][valid]
        varying = int(np.any(values != values[0], axis=0).sum()) if len(values) else 0
        transfers.append(
            dict(
                coordinates=key,
                parity=parity,
                qualified_frames=int(valid.sum()),
                errors=int(((observed != parity) & valid).sum()),
                varying_constituents=varying,
            )
        )
    summary.update(
        unique_exact_higher_relations=len(unique),
        raw_supported_relations=sum(r["qualified_frames"] >= 4 for r in transfers),
        raw_exact_supported_relations=sum(
            r["qualified_frames"] >= 4 and r["errors"] == 0 for r in transfers
        ),
        raw_exact_all_constituents_vary=sum(
            r["qualified_frames"] >= 4
            and r["errors"] == 0
            and r["varying_constituents"] == len(r["coordinates"])
            for r in transfers
        ),
    )
    output = dict(
        summary=summary,
        rows=rows,
        raw_transfers=transfers,
        raw_source_sha256=hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        limitation="Discovery-basis relations evaluated on later39 frames. "
        "Overlapping windows and relations are dependent. Evaluation-quality "
        "gate remains. Low-rank selection or surviving parity does not identify "
        "a code; low-diversity message states can yield accidental relations.",
    )
    (BASE / "local/header_rank_relations.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
