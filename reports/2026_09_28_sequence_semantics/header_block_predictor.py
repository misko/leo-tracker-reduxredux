"""Fit fixed affine bit predictors on discovery frames and audit later frames."""

import hashlib
import json
from pathlib import Path

import numpy as np
from header_rank_relations import column_words
from scipy.io import loadmat

BASE = Path(__file__).parent


def fit(bits):
    columns = column_words(bits ^ bits[0])
    pivots, basis, rules = {}, [], []
    for index, value in enumerate(columns):
        combination = 0
        while value:
            bit = value.bit_length() - 1
            if bit not in pivots:
                pivots[bit] = (value, combination ^ (1 << index))
                basis.append(index)
                break
            prior, mask = pivots[bit]
            value ^= prior
            combination ^= mask
        if not value:
            inputs = [i for i in range(bits.shape[1]) if combination >> i & 1]
            constant = int(bits[0, index])
            for i in inputs:
                constant ^= int(bits[0, i])
            rules.append(dict(output=index, inputs=inputs, constant=constant))
    return basis, rules


def evaluate(bits, valid, rules):
    result = []
    for rule in rules:
        ids = rule["inputs"] + [rule["output"]]
        good = valid[:, ids].all(axis=1)
        prediction = np.full(len(bits), rule["constant"], dtype=np.uint8)
        for i in rule["inputs"]:
            prediction ^= bits[:, i]
        result.append(
            dict(
                **rule,
                count=int(good.sum()),
                errors=int(((prediction != bits[:, rule["output"]]) & good).sum()),
            )
        )
    return result


def main():
    source = BASE / "local/header-reference-0-77.npz"
    template_path = (
        BASE.parents[1]
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement"
        / "reference-template/referenceTemplate.mat"
    )
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = np.load(source)["symbols"][:, 0] * np.exp(-0.5j * np.pi * template[:, 1])
    raw_path = BASE / "local/pilot_referenced_header_bits.npz"
    raw = np.load(raw_path)
    raw_map = {int(b): i for i, b in enumerate(raw["bins"])}
    rows = []
    for first, last in [(901, 938), (880, 994), (888, 1002)]:
        bins = np.arange(first, last)
        bits = (z[:, bins].real >= 0).astype(np.uint8)
        valid = (abs(z[:, bins].imag) < 0.05) & (abs(abs(z[:, bins].real) - 1) < 0.05)
        # Require entire discovery block quality; no imputation of erased inputs.
        qualified = valid[:39].all(axis=1)
        basis, rules = fit(bits[:39][qualified])
        held = evaluate(bits[39:], valid[39:], rules)
        raw_ids = [raw_map[int(b)] for b in bins]
        raw_eval = evaluate(raw["bits"][:, 0, raw_ids], raw["valid"][:, 0, raw_ids], rules)
        row = dict(
            bins=bins.tolist(),
            discovery_frames=int(qualified.sum()),
            combined_rank=len(fit(bits[valid.all(axis=1)])[0]),
            basis_bins=bins[basis].tolist(),
            rules=held,
            raw_rules=raw_eval,
            reference_exact=sum(r["count"] == 39 and not r["errors"] for r in held),
            reference_supported=sum(r["count"] == 39 for r in held),
            raw_exact=sum(r["count"] >= 4 and not r["errors"] for r in raw_eval),
            both_exact=sum(
                a["count"] == 39 and not a["errors"] and b["count"] >= 4 and not b["errors"]
                for a, b in zip(held, raw_eval, strict=True)
            ),
        )
        rows.append(row)
        print(
            json.dumps(
                {k: v for k, v in row.items() if k not in ("bins", "rules", "raw_rules")}, indent=2
            )
        )
    output = dict(
        rows=rows,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (source, template_path, raw_path)
        },
        limitation="Exploratory windows around previously selected equations, "
        "same public acquisition. Basis bits are empirical coordinates, not "
        "decoded source bits. Partial prediction is not a recovered encoder.",
    )
    (BASE / "local/header_block_predictor.json").write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
