"""Preserve each symbol's patterns while breaking matched-frame pairing."""

import hashlib
import json
from pathlib import Path

import numpy as np
from header_block_rank import rank
from header_rectangle_rank import packed_rows
from scipy.io import loadmat

BASE = Path(__file__).parent


def affine_rank(words):
    return rank([int(w) ^ int(words[0]) for w in words[1:]])


def paired_rank(left, right, width, shift=0):
    right = np.roll(right, shift)
    return affine_rank([int(a) | (int(b) << width) for a, b in zip(left, right, strict=True)])


def main():
    prior_path = BASE / "local/header_rectangle_rank.json"
    prior = json.loads(prior_path.read_text())
    for name, digest in prior["input_sha256"].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest
    source = BASE / "local/header-reference-0-77.npz"
    template_path = (
        BASE.parents[1]
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement"
        / "reference-template/referenceTemplate.mat"
    )
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = np.load(source)["symbols"] * np.exp(-0.5j * np.pi * template[:, 1:7].T)
    bits = z.real >= 0
    rows = []
    for c in prior["rows"]:
        if c["combined_rank"] is None or c["combined_rank"] > 32:
            continue
        symbols = [s - 2 for s in c["symbols"]]
        start, width = c["start_bin"], c["width"]
        a, b = [packed_rows(bits[:, s, start : start + width]) for s in symbols]
        observed = paired_rank(a, b, width)
        assert observed == c["combined_rank"]
        shifted = [paired_rank(a, b, width, shift) for shift in range(1, 78)]
        rows.append(
            dict(
                symbols=c["symbols"],
                start_bin=start,
                observed=observed,
                individual_rank_sum=affine_rank(a) + affine_rank(b),
                shifted_ranks=shifted,
                shifted_at_most32=int(sum(r <= 32 for r in shifted)),
                shifted_at_most_observed=int(sum(r <= observed for r in shifted)),
            )
        )
    summary = dict(
        windows=len(rows),
        shifts_per_window=77,
        observed_strictly_below_every_shift=sum(r["shifted_at_most_observed"] == 0 for r in rows),
        every_shift_still_at_most32=sum(r["shifted_at_most32"] == 77 for r in rows),
        no_shift_at_most32=sum(r["shifted_at_most32"] == 0 for r in rows),
        fraction_shifted_tests_at_most32=sum(r["shifted_at_most32"] for r in rows)
        / (77 * len(rows)),
    )
    output = dict(
        summary=summary,
        rows=rows,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (source, template_path, prior_path)
        },
        limitation="Circular frame shifts preserve each symbol pattern frequencies "
        "and cyclic temporal order, not cross-symbol alignment. Descriptive control "
        "on previously selected overlapping windows, not calibrated significance. "
        "Common message states can create cross-symbol dependence without FEC.",
    )
    (BASE / "local/rectangle_rank_control.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
