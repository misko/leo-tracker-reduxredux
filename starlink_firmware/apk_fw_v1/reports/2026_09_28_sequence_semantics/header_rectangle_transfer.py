"""Audit cross-symbol constraints in surviving rectangles on existing raw frames."""

import hashlib
import json
from pathlib import Path

import numpy as np
from header_block_predictor import evaluate, fit
from header_rectangle_rank import block
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent


def mixed(rule, width):
    return len(set(i // width for i in rule["inputs"] + [rule["output"]])) > 1


def main():
    rank_path = BASE / "local/header_rectangle_rank.json"
    prior = json.loads(rank_path.read_text())
    for path, digest in prior["input_sha256"].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    candidates = [
        r for r in prior["rows"] if r["combined_rank"] is not None and r["combined_rank"] <= 32
    ]
    source = BASE / "local/header-reference-0-77.npz"
    template_path = (
        BASE.parents[3]
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement"
        / "reference-template/referenceTemplate.mat"
    )
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = np.load(source)["symbols"] * np.exp(-0.5j * np.pi * template[:, 1:7].T)
    bits = (z.real >= 0).astype(np.uint8)
    raw_path = BASE / "local/pilot_referenced_header_bits.npz"
    raw = np.load(raw_path)
    raw_map = {int(b): i for i, b in enumerate(raw["bins"])}
    rows, unique = [], {}
    for candidate in candidates:
        symbols = [s - 2 for s in candidate["symbols"]]
        start, width = candidate["start_bin"], candidate["width"]
        values = block(bits, symbols, start, width)
        _, rules = fit(values)
        cross = [r for r in rules if mixed(r, width)]
        ids = [raw_map[b] for b in range(start, start + width)]
        raw_bits = raw["bits"][:, symbols][:, :, ids].reshape(7, -1)
        raw_valid = raw["valid"][:, symbols][:, :, ids].reshape(7, -1)
        results = evaluate(raw_bits, raw_valid, cross)
        for rule, result in zip(cross, results, strict=True):
            positions = sorted(rule["inputs"] + [rule["output"]])
            coords = tuple((symbols[p // width] + 2, start + p % width) for p in positions)
            good = raw_valid[:, positions].all(axis=1)
            v = raw_bits[good][:, positions]
            variable = np.any(v != v[0], axis=0) if len(v) else np.zeros(len(positions), bool)
            varying_symbols = sorted(set(coords[i][0] for i in np.flatnonzero(variable)))
            record = dict(
                coordinates=coords,
                parity=rule["constant"],
                count=result["count"],
                errors=result["errors"],
                varying_constituents=int(variable.sum()),
                varying_symbols=varying_symbols,
            )
            if coords in unique:
                assert unique[coords] == record
            unique[coords] = record
        fullgood = raw_valid.all(axis=1)
        combined_rank = len(fit(np.concatenate([values, raw_bits[fullgood]]))[0])
        ref_words = set(np.packbits(v).tobytes() for v in values)
        new_words = set(np.packbits(v).tobytes() for v in raw_bits[fullgood])-ref_words
        rows.append(
            dict(
                **candidate,
                mixed_rules=len(cross),
                raw_full_frames=int(fullgood.sum()),
                rank_with_qualified_raw=combined_rank,
                novel_raw_words=len(new_words),
            )
        )
    relations = list(unique.values())
    supported = [r for r in relations if r["count"] >= 4]
    exact = [r for r in supported if not r["errors"]]
    summary = dict(
        rectangles=len(rows),
        unique_mixed_relations=len(relations),
        supported=len(supported),
        exact=len(exact),
        exact_with_both_symbols_varying=sum(len(r["varying_symbols"]) == 2 for r in exact),
        rectangles_raw_rank_over32=sum(r["rank_with_qualified_raw"] > 32 for r in rows),
    )
    output = dict(
        summary=summary,
        rows=rows,
        relations=relations,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (source, template_path, raw_path, rank_path)
        },
        limitation="Relations fitted to all78 reference frames after rank selection; "
        "raw transfer is different frames/processing, same acquisition. "
        "Overlapping relations dependent; limited raw diversity remains a risk.",
    )
    (BASE / "local/header_rectangle_transfer.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
