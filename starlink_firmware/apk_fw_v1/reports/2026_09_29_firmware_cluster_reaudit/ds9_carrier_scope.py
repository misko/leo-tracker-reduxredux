"""Attribute frozen DS9 early-Q covariance to the two recorded carrier groups."""

import json
from pathlib import Path

import numpy as np
from ds9_axis_audit import rotations
from ds9_leakage_transfer import BASE, METHOD, load_correction, source


def contributions(a, b, bins):
    a, b = a - a.mean(axis=0), b - b.mean(axis=0)
    total = float(np.sum(a * b))
    rows = []
    for name, mask in (("516-527", (bins >= 516) & (bins <= 527)),
                       ("536-547", (bins >= 536) & (bins <= 547))):
        if mask.sum() != 12:
            raise ValueError("Expected both complete 12-carrier groups")
        x, y = a[..., mask], b[..., mask]
        covariance = float(np.sum(x * y))
        energy = [float(np.sum(v ** 2)) for v in (x, y)]
        rows.append(dict(group=name, carriers=bins[mask].tolist(), covariance=covariance,
                         covariance_fraction=covariance / total if total else None,
                         energies=energy, correlation=float(rotations(x, y)[0])))
    np.testing.assert_allclose(sum(r["covariance"] for r in rows), total, atol=1e-10)
    return rows


def main():
    path = BASE / "local/ds9-leakage-transfer.json"
    previous = json.loads(path.read_text())
    correct = load_correction()
    visits = []
    for visit in previous["visits"]:
        cache = Path(visit["source"]["path"])
        assert source(cache) == visit["source"]
        train, held = visit["discovery_frames"], visit["evaluation_frames"]
        with np.load(cache) as data:
            bins = data["bins0"]
            assert np.array_equal(bins, data["bins1"])
            values = [correct(data[f"z{rx}"][train, :6].astype(np.complex128),
                              data[f"z{rx}"][held, :6].astype(np.complex128)) for rx in (0, 1)]
        rows, controls = [], []
        for name, k in (("Q", 1), ("Q_after_I_regression", 2)):
            a, b = [v[k] for v in values]
            for row in contributions(a, b, bins):
                mask = np.isin(bins, row["carriers"])
                x, y = a[..., mask], b[..., mask]
                scores = rotations(x, y)
                controls.append(scores)
                leave_one = [float(rotations(np.delete(x, f, axis=0),
                                             np.delete(y, f, axis=0))[0]) for f in range(len(held))]
                row.update(component=name,
                           leave_one_frame_out_range=[min(leave_one), max(leave_one)])
                rows.append(row)
        maxima = np.abs(controls).max(axis=0)
        for row in rows:
            row["two_excerpt_family_rank"] = min(1., 2 * float(np.mean(
                maxima >= abs(row["correlation"]) - 1e-12)))
        visits.append(dict(visit=visit["visit"], source=source(cache), frames=held, rows=rows))
    result = dict(visits=visits, source=source(path), method=source(Path(__file__)),
                  preprocessing_source=source(METHOD),
                  limitation="Two fixed contiguous carrier groups around the lower pilot, "
                  "physical symbols2–7 only; no coordinate search. Four-assay maximum per "
                  "excerpt, then Bonferroni over two excerpts. Covariance fractions are "
                  "signed descriptive contributions, not probabilities. Leave-one-frame-out "
                  "ranges are influence diagnostics, not confidence intervals. Frames already "
                  "examined; same calibration and cyclic-reference limitations apply. "
                  "Neither group corresponds to an established software field or satellite.")
    (BASE / "local/ds9-carrier-scope.json").write_text(json.dumps(result, indent=2) + "\n")
    for visit in visits:
        print(visit["visit"])
        for r in visit["rows"]:
            print(r["component"], r["group"], r["correlation"], r["covariance_fraction"],
                  r["leave_one_frame_out_range"], r["two_excerpt_family_rank"])


if __name__ == "__main__":
    main()
