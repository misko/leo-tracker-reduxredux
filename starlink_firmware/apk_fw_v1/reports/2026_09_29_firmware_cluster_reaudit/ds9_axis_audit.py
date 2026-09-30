"""Reproduce DS9 axis associations and jointly control frozen regions/axes."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
OLD = (BASE.parents[3] / "reports") / "2026_09_28_sequence_semantics/local"


def rotations(x, y):
    a, b = x - x.mean(axis=0), y - y.mean(axis=0)
    denominator = np.sqrt(np.sum(a * a) * np.sum(b * b))
    if denominator == 0:
        raise ValueError("Constant axis: correlation undefined")
    return np.array([np.sum(a * np.roll(b, s, axis=0)) / denominator for s in range(len(a))])


def main():
    path = OLD / "ds9_header_quadrature.json"
    receipt = json.loads(path.read_text())
    for p, sha in receipt["input_sha256"].items():
        assert hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
    reliability = json.loads((OLD / "ds9_combined_reliability.json").read_text())
    output = []
    for visit in ("middle", "last"):
        frames = reliability["per_visit"][visit]["evaluation_frames"]
        originals = [r for r in receipt["rows"] if r["visit"] == visit]
        assays, controls = [], []
        with np.load(OLD / f"DS9-{visit}-soft.npz") as data:
            for r in originals:
                name = r["region"]
                start, stop = ((0, 6) if name == "header_all" else (270, 300)
                               if name == "tail" else (int(name[7:]) - 2, int(name[7:]) - 1))
                for axis in ("real", "imag"):
                    a, b = [getattr(data[f"z{i}"][frames, start:stop], axis) for i in (0, 1)]
                    scores = rotations(a, b)
                    expected = r["axes"][axis]
                    np.testing.assert_allclose([scores[0], scores[1:].mean(), scores[1:].min(),
                                               scores[1:].max()],
                                              [expected["correlation"], expected["shifted_mean"],
                                               *expected["shifted_range"]], atol=1e-10)
                    assays.append(dict(region=name, axis=axis, correlation=float(scores[0])))
                    controls.append(scores)
        matrix = np.array(controls)
        maxima = abs(matrix).max(axis=0)
        for row in assays:
            rank = float(np.mean(maxima >= abs(row["correlation"]) - 1e-12))
            row.update(within_excerpt_axis_region_max_rank=rank,
                       two_excerpt_bonferroni_rank=min(1., 2 * rank))
        output.append(dict(visit=visit, frames=frames, assays=assays,
                           circular_family_maxima=maxima.tolist()))
    result = dict(visits=output,
                  source=dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()),
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Existing DS9 frozen regions/axes, no fit or coordinate search. "
                  "Coordinate centering only: unlike DS10 common-level/template-gain removal. "
                  "RX1 jointly rotates within each excerpt, max over 16 tests then Bonferroni "
                  "over two excerpts. Conditional coarse cyclic ranks, not independent trials; "
                  "frame gaps and shared calibration remain limitations. No message-bit claim.")
    (BASE / "local/ds9-axis-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    for v in output:
        print(v["visit"], len(v["frames"]),
              [(r["axis"], round(r["correlation"], 4), r["two_excerpt_bonferroni_rank"])
               for r in v["assays"] if r["region"] == "header_all"])


if __name__ == "__main__":
    main()
