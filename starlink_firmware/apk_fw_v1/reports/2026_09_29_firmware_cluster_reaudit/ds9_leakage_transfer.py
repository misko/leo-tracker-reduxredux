"""Apply the frozen DS10 axis correction to DS9, without coordinate search."""

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
from ds9_axis_audit import rotations

BASE = Path(__file__).resolve().parent
OLD = (BASE.parents[3] / "reports") / "2026_09_28_sequence_semantics/local"
METHOD = (BASE.parents[3] / "reports") / "2026_09_29_ds10_signal_extension/early_iq.py"


def load_correction():
    spec = importlib.util.spec_from_file_location("frozen_early_iq", METHOD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.remove_offset_and_leakage


def source(path):
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def main():
    correct = load_correction()
    reliability_path = OLD / "ds9_combined_reliability.json"
    reference_path = OLD / "ds9_header_quadrature.json"
    reference = json.loads(reference_path.read_text())
    for path, digest in reference["input_sha256"].items():
        assert source(Path(path))["sha256"] == digest
    reliability = json.loads(reliability_path.read_text())
    visits = []
    for name in ("middle", "last"):
        split = reliability["per_visit"][name]
        train, held = split["discovery_frames"], split["evaluation_frames"]
        assert set(train).isdisjoint(held) and max(train) < min(held)
        path = OLD / f"DS9-{name}-soft.npz"
        with np.load(path) as data:
            assert np.array_equal(data["bins0"], data["bins1"])
            assert not set(data["bins0"]) & (set(range(488, 496)) | set(range(528, 536)))
            values = [correct(data[f"z{rx}"][train, :6].astype(np.complex128),
                              data[f"z{rx}"][held, :6].astype(np.complex128)) for rx in (0, 1)]
        rows, controls = [], []
        for component, k in (("I_centered", 0), ("Q_centered", 1),
                             ("Q_after_local_I_regression", 2)):
            for first, stop in [(0, 6), *[(i, i + 1) for i in range(6)]]:
                a, b = [v[k][:, first:stop] for v in values]
                scores = rotations(a, b)
                controls.append(scores)
                rows.append(dict(component=component, symbols=[first + 2, stop + 1],
                                 correlation=float(scores[0]),
                                 residual_energy=[float(np.mean(x ** 2)) for x in (a, b)]))
        maxima = np.abs(controls).max(axis=0)
        for row in rows:
            row["two_excerpt_family_rank"] = min(1., 2 * float(np.mean(
                maxima >= abs(row["correlation"]) - 1e-12)))
        visits.append(dict(visit=name, source=source(path), discovery_frames=train,
                           evaluation_frames=held, rows=rows,
                           circular_family_maxima=maxima.tolist()))
    output = dict(visits=visits, sources=[source(METHOD), source(reliability_path),
                                         source(reference_path), source(Path(__file__))],
                  limitation="Frozen DS10 per-coordinate real-to-imaginary regression, fit "
                  "separately per receiver on chronological discovery frames. No slope, "
                  "axis, coordinate, or confidence search. Max over 21 assays per excerpt "
                  "then Bonferroni for two excerpts. Previously examined reserved frames "
                  "are not new independent confirmation. Cyclic exchangeability and "
                  "irregular frame gaps limit ranks; minimum corrected rank is 2/23. "
                  "Removing I-correlated Q can remove modulation as well as leakage. "
                  "Shared residual Q does not establish message bits or satellite identity.")
    (BASE / "local/ds9-leakage-transfer.json").write_text(json.dumps(output, indent=2) + "\n")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.5), sharey=True, layout="constrained")
    for ax, visit in zip(axes, visits, strict=True):
        for component, label in (("I_centered", "I"), ("Q_centered", "Q"),
                                 ("Q_after_local_I_regression", "Q after I regression")):
            rows = [r for r in visit["rows"] if r["component"] == component
                    and r["symbols"][0] == r["symbols"][1]]
            ax.plot([r["symbols"][0] for r in rows], [r["correlation"] for r in rows],
                    "o-", label=label)
        ax.axhline(0, color="gray", linewidth=.8)
        ax.set(title=f"DS9 {visit['visit']}: 23 reserved frames", xlabel="Physical OFDM symbol")
    axes[0].set_ylabel("Cross-receiver correlation")
    axes[1].legend(fontsize=8)
    fig.savefig(BASE / "local/ds9-leakage-transfer.png", dpi=160)
    plt.close(fig)
    for v in visits:
        print(v["visit"], [(r["component"], r["correlation"], r["two_excerpt_family_rank"])
                            for r in v["rows"] if r["symbols"] == [2, 7]])


if __name__ == "__main__":
    main()
