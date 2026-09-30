"""Predict symbols5–7 from state-conditioned templates trained on earlier frames."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent


def templates(bits, valid, labels, minimum=3):
    models = {}
    for label in np.unique(labels):
        keep = labels == label
        count = valid[keep].sum(axis=0)
        ones = (bits[keep] * valid[keep]).sum(axis=0)
        models[int(label)] = (ones * 2 >= count, count >= minimum)
    return models


def main():
    state_path = BASE / "local/shared_header_coordinates.json"
    states = np.array(json.loads(state_path.read_text())["reference_state_indices"])
    source = BASE / "local/header-reference-0-77.npz"
    tp = (
        BASE.parents[3]
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement"
        / "reference-template/referenceTemplate.mat"
    )
    bins = np.array(
        [b for b in range(2, 1022) if b not in range(488, 496) and b not in range(528, 536)]
    )
    template = loadmat(tp)["referenceTemplateRotations"]
    # All defining coordinates belong to symbols2–4. Exclude them completely.
    z = np.load(source)["symbols"][:, 3:6][:, :, bins] * np.exp(
        -0.5j * np.pi * template[bins, 4:7].T
    )
    bits = z.real >= 0
    valid = (abs(z.imag) < 0.05) & (abs(abs(z.real) - 1) < 0.05)
    models = templates(bits[:39], valid[:39], states[:39])
    baseline, _ = templates(bits[:39], valid[:39], np.zeros(39, int))[0]
    frequency = (bits[:39] * valid[:39]).sum(axis=0) / np.maximum(valid[:39].sum(axis=0), 1)
    variable = (frequency >= 0.2) & (frequency <= 0.8)
    rows = []
    unknown = []
    for frame in range(39, 78):
        if int(states[frame]) not in models:
            unknown.append(frame)
            continue
        prediction, support = models[int(states[frame])]
        for s in range(3):
            keep = support[s] & valid[frame, s] & variable[s]
            rows.append(
                dict(
                    frame=frame,
                    state=int(states[frame]),
                    symbol=s + 5,
                    count=int(keep.sum()),
                    conditional_errors=int((prediction[s] != bits[frame, s])[keep].sum()),
                    baseline_errors=int((baseline[s] != bits[frame, s])[keep].sum()),
                )
            )
    summaries = []
    for s in range(5, 8):
        selected = [r for r in rows if r["symbol"] == s]
        count = sum(r["count"] for r in selected)
        summaries.append(
            dict(
                symbol=s,
                count=count,
                conditional_error_fraction=sum(r["conditional_errors"] for r in selected) / count
                if count
                else None,
                baseline_error_fraction=sum(r["baseline_errors"] for r in selected) / count
                if count
                else None,
            )
        )
    output = dict(
        summary=summaries,
        unknown_state_frames=unknown,
        rows=rows,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, tp, state_path)
        },
        limitation="Prediction templates fitted onlyfirst39frames; evaluate later39 "
        "on symbols5–7 disjoint from state-defining symbols2–4. States themselves "
        "were discovered using all78frames, so not fully independent validation. "
        "Only discovery-variable coordinates, at least3 qualified same-state "
        "training observations. Unknown states abstain. No protocol semantics.",
    )
    (BASE / "local/state_conditioned_header.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(dict(summary=summaries, unknown_state_frames=unknown), indent=2))


if __name__ == "__main__":
    main()
