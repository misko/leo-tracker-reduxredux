"""Frozen early-IQ receiver comparisons, joint cyclic control across excerpts."""

import hashlib
import itertools
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
SOURCE = BASE.parents[3] / "reports/2026_09_29_ds10_signal_extension/local/within-visit/early-iq"


def correlation(a, b):
    a = np.asarray(a, dtype=float) - np.mean(a, axis=0)
    b = np.asarray(b, dtype=float) - np.mean(b, axis=0)
    return float(np.sum(a * b) / max(np.linalg.norm(a) * np.linalg.norm(b), 1e-20))


def arrays(data, row):
    name = row["component"]
    if name == "I_without_common_level_or_template_gain":
        pair = [data[f"detrended_i{rx}"] for rx in range(2)]
    elif name == "I_without_common_carrier_level":
        pair = [data[f"rx{rx}"][0] for rx in range(2)]
        pair = [x - x.mean(axis=2, keepdims=True) for x in pair]
    else:
        index = ["I_centered", "Q_centered", "Q_after_local_I_regression"].index(name)
        pair = [data[f"rx{rx}"][index] for rx in range(2)]
    lo, hi = row["symbols"]
    return [x[:, lo - 2:hi - 1] for x in pair]


def coupled_reference(matrices):
    boundaries = sorted({k / m.shape[1] for m in matrices for k in range(m.shape[1] + 1)})
    weights = np.diff(boundaries)
    midpoints = (np.array(boundaries[:-1]) + boundaries[1:]) / 2
    coupled = np.array([np.mean([m[:, int(u * m.shape[1])] for m in matrices], axis=0)
                        for u in midpoints])
    return coupled, weights


def main():
    receipt = SOURCE / "summary.json"
    summary = json.loads(receipt.read_text())
    matrices, visits, keys = [], [], None
    for visit in summary["visits"]:
        path = SOURCE / f"{visit['visit']}.npz"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == visit["output_sha256"]
        current_keys = [(r["component"], r["symbols"]) for r in visit["rows"]]
        assert keys is None or keys == current_keys
        keys = current_keys
        with np.load(path) as data:
            n = len(data["frames"])
            scores = []
            for row in visit["rows"]:
                a, b = arrays(data, row)
                values = [correlation(a, np.roll(b, shift, axis=0)) for shift in range(n)]
                assert abs(values[0] - row["centered_correlation"]) < 1e-6
                scores.append(values)
        matrices.append(np.array(scores))
        visits.append(dict(visit=visit["visit"], frames=visit["evaluation_frames"], sha256=digest))
    # A visit's receiver rotates as one block, preserving all coordinate and
    # component dependencies. Excerpts have separate rotation offsets.
    combinations = list(itertools.product(*(range(m.shape[1]) for m in matrices)))
    references = np.array([np.mean([m[:, k] for m, k in zip(matrices, shifts, strict=True)], axis=0)
                           for shifts in combinations])
    centered = references - references.mean(axis=0)
    maxima = abs(centered).max(axis=1)
    observed = centered[0]
    family_p = (maxima[:, None] >= abs(observed)[None, :] - 1e-12).mean(axis=0)
    # Sensitivity to shared session structure: use one fractional cycle for
    # all excerpts, integrating exactly over its unequal-length intervals.
    coupled, weights = coupled_reference(matrices)
    coupled_centered = coupled - weights @ coupled
    coupled_max = abs(coupled_centered).max(axis=1)
    coupled_p = weights @ (coupled_max[:, None] >= abs(coupled_centered[0])[None, :] - 1e-12)
    results = [dict(component=name, symbols=symbols,
                    visit_correlations=[float(m[i, 0]) for m in matrices],
                    equal_visit_mean=float(references[0, i]),
                    cyclic_centered_mean=float(observed[i]), family_p=float(family_p[i]),
                    coupled_session_family_p=float(coupled_p[i]))
               for i, (name, symbols) in enumerate(keys)]
    output = dict(visits=visits, rows=results, tests=len(results), rotations=len(combinations),
                  coupled_intervals=len(weights), coupled_interval_weights=weights.tolist(),
                  receipt_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest(),
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Frozen 34 component/region comparisons and discovery-only "
                  "preprocessing. Two-sided max-stat cyclic reference, equal excerpt weights. "
                  "Three excerpts share a session and calibration assumptions; not three "
                  "independent satellite passes. Irregular qualified-frame gaps and cyclic "
                  "exchangeability limit inference. Previously examined held data, correction "
                  "only this family. Receiver agreement does not identify satellite/message.")
    (BASE / "local/receiver-family.json").write_text(json.dumps(output, indent=2) + "\n")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4), layout="constrained")
    for component, label in [("I_centered", "I: discovery mean removed"),
                              ("I_without_common_level_or_template_gain", "I: level/gain removed"),
                              ("Q_after_local_I_regression", "Q: fitted I leakage removed")]:
        selected = [r for r in results if r["component"] == component
                    and r["symbols"][0] == r["symbols"][1]]
        ax.plot([r["symbols"][0] for r in selected], [r["equal_visit_mean"] for r in selected],
                "o-", label=label)
    ax.axhline(0, color="gray", linewidth=.8)
    ax.set(xlabel="Physical OFDM symbol", ylabel="Mean cross-receiver correlation",
           title="Three DS10 excerpts: shared early real-axis structure")
    ax.legend(fontsize=8)
    fig.savefig(BASE / "local/receiver-family.png", dpi=160)
    plt.close(fig)
    print("Tests", len(results), "rotations", len(combinations))
    for r in results:
        if r["family_p"] < .05:
            print(r["component"], r["symbols"], round(r["equal_visit_mean"], 3),
                  r["family_p"], r["coupled_session_family_p"])


if __name__ == "__main__":
    main()
