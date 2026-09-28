"""Predict every tail sign from power-derived boundaries, without fitting words."""

import hashlib
import json
from pathlib import Path

import numpy as np
from region_phase_audit import WORDS
from scipy.io import loadmat

BASE = Path(__file__).parent


def predicted_signs(boundary, positions):
    # n=(symbol-2)*1004+carrier; slot=carrier-16*symbol == n-32 (mod60).
    return WORDS[(-boundary) % 60, (positions - 32) % 60]


def compare(values, prediction):
    valid = np.isfinite(values)
    actual = values.real >= 0
    expected = prediction >= 0
    return dict(decisions=int(valid.sum()), errors=int(((actual != expected) & valid).sum()))


def main():
    soft_path = BASE / "local/full-soft-reference-0-12.npz"
    boundary_path = BASE / "local/soft_tail_boundary.json"
    raw_path = BASE / "local/pilot_polarity.npz"
    raw_boundary_path = BASE / "local/raw_tail_boundary.json"
    template_path = (
        BASE.parents[1]
        / "docs/research/starlink-literature/local/data/ut-pilots"
        / "supplement/reference-template/referenceTemplate.mat"
    )
    bins = np.array(
        [
            k
            for k in np.argsort(np.fft.fftfreq(1024))
            if 2 <= k < 1022 and k not in range(488, 496) and k not in range(528, 536)
        ]
    )
    template = loadmat(template_path)["referenceTemplateRotations"]
    reference = np.load(soft_path)["symbols"][:, 1:][:, :, bins] * np.exp(
        -0.5j * np.pi * template[bins, 1:].T
    )
    cases = [
        ("reference", r["frame"], None, r["boundary"], reference[r["frame"]].ravel())
        for r in json.loads(boundary_path.read_text())["rows"]
        if r["flank"] == 502
    ]
    raw = np.load(raw_path)
    order = np.argsort(np.fft.fftfreq(1024)[raw["bins"]])
    cases += [
        (
            "raw",
            r["frame"],
            r["edge"],
            r["boundary"],
            raw["deviations"][r["frame"] - 250, r["edge"]][:, order].ravel(),
        )
        for r in json.loads(raw_boundary_path.read_text())["rows"]
        if r["eligible"]
    ]
    rows = []
    for source, frame, edge, boundary, values in cases:
        for label, start, stop in (
            ("before240", boundary - 240, boundary),
            ("first240", boundary, boundary + 240),
            ("remaining_tail", boundary + 240, len(values)),
        ):
            positions = np.arange(start, stop)
            prediction = predicted_signs(boundary, positions)
            rows.append(
                dict(
                    source=source,
                    frame=frame,
                    edge=edge,
                    region=label,
                    boundary=boundary,
                    **compare(values[start:stop], prediction),
                    plus_one_control=compare(
                        values[start:stop], predicted_signs(boundary + 1, positions)
                    ),
                )
            )
    summary = []
    for source in ("reference", "raw"):
        for region in ("before240", "first240", "remaining_tail"):
            selected = [r for r in rows if r["source"] == source and r["region"] == region]
            summary.append(
                dict(
                    source=source,
                    region=region,
                    decisions=sum(r["decisions"] for r in selected),
                    errors=sum(r["errors"] for r in selected),
                    control_errors=sum(r["plus_one_control"]["errors"] for r in selected),
                )
            )
    result = dict(
        rows=rows,
        summary=summary,
        polarity=1,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (soft_path, boundary_path, raw_path, raw_boundary_path, template_path)
        },
        limitation="No phase or polarity fitting. Generator and boundary relation "
        "were discovered on this acquisition; this is expanded verification, "
        "not a fresh blind test. Raw edge estimates share samples. A boundary "
        "shift of60 predicts identical signs; signs alone cannot locate absolute "
        "boundary. Disagreements are model errors, not validated transmitted BER.",
    )
    (BASE / "local/boundary_tail_prediction.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
