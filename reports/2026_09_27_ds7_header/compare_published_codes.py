"""Compare independently recovered DS7 codes with published UT hard symbols."""

import hashlib
import json
from pathlib import Path

import numpy as np
from recover import references
from tcodes import fit_code, score_code, select_window, slots


def distance_modulo_rotation_polarity(a, b):
    distances = [int(np.sum(a != np.roll(b, shift))) for shift in range(60)]
    return min(min(distances), 60 - max(distances))


def main():
    out = Path(__file__).parent / "local"
    source_path = out / "ut-reference/decoded-upper-806-818.npz"
    inventory = json.loads((out / "ut-reference/inventory.json").read_text())
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == inventory["output_sha256"]
    source = np.load(source_path)
    bins = source["bins"]
    _, template, _ = references()
    ds7 = []
    for group in ("best-upper", "holdout-upper"):
        for row in json.loads((out / group / "tcodes.json").read_text())["results"]:
            ds7.append((group, row["frame"], np.array([int(b) for b in row["combined_word"]])))
    results = []
    for frame, sy in zip(source["zero_based_frames"], source["symbols"], strict=True):
        deviations = sy[1:] * template[bins, 1:].T.conj()
        first, score, _ = select_window(deviations, bins)
        mapping = slots(bins, np.arange(first, first + 64))
        window = deviations[first - 2 : first + 62]
        code, _, _ = fit_code(window, mapping)
        bits = (code > 0).astype(int)
        distances = [distance_modulo_rotation_polarity(bits, b) for _, _, b in ds7]
        results.append(
            dict(
                ut_zero_based_frame=int(frame),
                first_symbol=first,
                selection_score=score,
                full_score=score_code(window, mapping, code),
                word="".join(str(b) for b in bits),
                minimum_ds7_distance=min(distances),
                exact_ds7_matches=[
                    dict(group=g, frame=f)
                    for (g, f, _), d in zip(ds7, distances, strict=True)
                    if d == 0
                ],
            )
        )
    result = dict(
        reference_sha256=inventory["output_sha256"],
        results=results,
        equivalence="Compare all cyclic rotations and global inversion, never arbitrary bit flips.",
        limitation="An exact family match validates pattern recovery; it does not identify "
        "the DS7 satellite or interpret metadata. "
        "Low-score reference windows are not qualified codes.",
    )
    (out / "published-code-comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    for row in results:
        print(
            row["ut_zero_based_frame"],
            round(row["full_score"], 3),
            row["minimum_ds7_distance"],
            len(row["exact_ds7_matches"]),
        )


if __name__ == "__main__":
    main()
