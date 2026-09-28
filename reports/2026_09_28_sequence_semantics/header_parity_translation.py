"""Test fixed nine-position parity shapes across carrier translations."""

import hashlib
import json
from pathlib import Path

import numpy as np
from header_block_rank import rank
from scipy.io import loadmat

BASE = Path(__file__).parent


def parity_check(bits, valid):
    qualified = valid.all(axis=1)
    parity = np.bitwise_xor.reduce(bits, axis=1)
    train = qualified[:39]
    if not train.any():
        return None
    constant = int(parity[:39][train][0])
    return dict(
        discovery_count=int(train.sum()),
        discovery_errors=int((parity[:39][train] != constant).sum()),
        evaluation_count=int(qualified[39:].sum()),
        evaluation_errors=int((parity[39:][qualified[39:]] != constant).sum()),
        parity=constant,
        discovery_varying=int(np.any(bits[:39][train] != bits[:39][train][0], axis=0).sum()),
    )


def main():
    prior = json.loads((BASE / "local/header_rank_relations.json").read_text())
    candidates = [
        r
        for r in prior["raw_transfers"]
        if r["errors"] == 0
        and r["qualified_frames"] >= 4
        and r["varying_constituents"] == len(r["coordinates"])
    ]
    source = BASE / "local/header-reference-0-77.npz"
    template_path = (
        BASE.parents[1]
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement"
        / "reference-template/referenceTemplate.mat"
    )
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = np.load(source)["symbols"] * np.exp(-0.5j * np.pi * template[:, 1:7].T)
    bits = (z.real >= 0).astype(np.uint8)
    valid = (abs(z.imag) < 0.05) & (abs(abs(z.real) - 1) < 0.05)
    raw = np.load(BASE / "local/pilot_referenced_header_bits.npz")
    raw_bins = {int(b): i for i, b in enumerate(raw["bins"])}
    allowed = set(raw_bins)
    rows, originals = [], []
    for index, candidate in enumerate(candidates):
        coords = candidate["coordinates"]
        assert len(set(s for s, b in coords)) == 1
        symbol = coords[0][0]
        original = np.array([b for s, b in coords])
        block = bits[:, symbol, original]
        words = [
            int.from_bytes(np.packbits(row, bitorder="little").tobytes(), "little") for row in block
        ]
        originals.append(
            dict(
                candidate=index,
                affine_rank=rank([w ^ words[0] for w in words]),
                distinct_words=len(set(words)),
                novel_evaluation_words=len(set(words[39:]) - set(words[:39])),
            )
        )
        for delta in range(2 - int(original.min()), 1022 - int(original.max())):
            bins = original + delta
            if not set(bins).issubset(allowed):
                continue
            result = parity_check(bits[:, symbol, bins], valid[:, symbol, bins])
            if result is None:
                continue
            raw_ids = [raw_bins[int(b)] for b in bins]
            good = raw["valid"][:, symbol, raw_ids].all(axis=1)
            raw_parity = np.bitwise_xor.reduce(raw["bits"][:, symbol, raw_ids], axis=1)
            rows.append(
                dict(
                    candidate=index,
                    delta=delta,
                    bins=bins.tolist(),
                    **result,
                    raw_count=int(good.sum()),
                    raw_errors=int((raw_parity[good] != result["parity"]).sum()),
                )
            )
    # This is cached decoder coverage, not a claim about all RF coverage in the corpus.
    coverage = []
    paths = sorted((BASE / "local").glob("S*-soft.npz")) + sorted(
        (BASE / "local").glob("DS9-*-soft.npz")
    )
    for path in paths:
        data = np.load(path)
        common = set(data["bins0"]) & set(data["bins1"])
        coverage.append(
            dict(
                signal=path.stem,
                carriers=sorted(int(b) for b in common),
                candidates_covered=[
                    i
                    for i, c in enumerate(candidates)
                    if set(b for s, b in c["coordinates"]).issubset(common)
                ],
            )
        )
    supported = [
        r
        for r in rows
        if r["discovery_count"] == 39
        and r["evaluation_count"] == 39
        and r["discovery_varying"] == 9
    ]
    exact = [r for r in supported if not r["discovery_errors"] and not r["evaluation_errors"]]
    summary = dict(
        translations=len(rows),
        fully_qualified_changing=len(supported),
        exact_reference=len(exact),
        exact_with_raw_support=sum(r["raw_count"] >= 4 and r["raw_errors"] == 0 for r in exact),
        exact_deltas=[[r["candidate"], r["delta"]] for r in exact],
    )
    output = dict(
        summary=summary,
        original_pattern_diversity=originals,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                source,
                template_path,
                BASE / "local/pilot_referenced_header_bits.npz",
                BASE / "local/header_rank_relations.json",
            )
        },
        rows=rows,
        cached_local_coverage=coverage,
        limitation="Post-selection exploratory translation test on reused reference "
        "and raw frames. Fixed parity learned separately at each translation "
        "from discovery; not a fresh independent confirmation. No new RF data.",
    )
    (BASE / "local/header_parity_translation.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
