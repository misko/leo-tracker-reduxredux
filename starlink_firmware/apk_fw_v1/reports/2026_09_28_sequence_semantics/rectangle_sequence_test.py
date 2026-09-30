"""Test the existing 60-state generator against two-symbol header rectangles."""

import hashlib
import json
from pathlib import Path

import numpy as np
from region_phase_audit import WORDS
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent


def fit_predict(observed, predictions, fit_count):
    scores = observed[:, :fit_count] @ predictions[:, :fit_count].T
    phases = np.argmax(abs(scores), axis=1)
    polarity = np.where(scores[np.arange(len(scores)), phases] >= 0, 1, -1)
    return predictions[phases] * polarity[:, None], phases, polarity


def main():
    prior_path = BASE / "local/header_rectangle_rank.json"
    prior = json.loads(prior_path.read_text())
    for name, digest in prior["input_sha256"].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest
    source = BASE / "local/header-reference-0-77.npz"
    template_path = (
        BASE.parents[3]
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement"
        / "reference-template/referenceTemplate.mat"
    )
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = np.load(source)["symbols"] * np.exp(-0.5j * np.pi * template[:, 1:7].T)
    signs = np.where(z.real >= 0, 1, -1).astype(np.int16)
    physical = [
        int(k)
        for k in np.argsort(np.fft.fftfreq(1024))
        if 2 <= k < 1022 and k not in range(488, 496) and k not in range(528, 536)
    ]
    compact = {b: i for i, b in enumerate(physical)}
    rows = []
    for c in prior["rows"]:
        if c["combined_rank"] is None or c["combined_rank"] > 32:
            continue
        bins = np.arange(c["start_bin"], c["start_bin"] + c["width"])
        symbols = np.array(c["symbols"])
        observed = signs[:, symbols - 2][:, :, bins].reshape(78, -1)
        slots = np.array(
            [[(compact[int(b)] - 16 * s) % 60 for b in bins] for s in symbols]
        ).reshape(-1)
        predictions = WORDS[:, slots]
        predicted, phases, polarity = fit_predict(observed, predictions, 28)
        baseline = np.where(observed[:, :28].sum(axis=1) >= 0, 1, -1)[:, None]
        # Discovery variability selects coordinates; held-out frames report errors.
        variable = np.any(observed[:39] != observed[0], axis=0)
        held_positions = np.arange(114) >= 28
        keep = held_positions & variable
        errors = predicted != observed
        rows.append(
            dict(
                symbols=c["symbols"],
                start_bin=c["start_bin"],
                complete_exact_frames=int((~errors.any(axis=1)).sum()),
                exact_nonconstant_frames=int(
                    ((~errors.any(axis=1)) & np.any(observed != observed[:, :1], axis=1)).sum()
                ),
                evaluation_count=int(39 * keep.sum()),
                evaluation_errors=int(errors[39:, keep].sum()),
                baseline_errors=int((baseline[39:] != observed[39:])[:, keep].sum()),
                fit_errors=int(errors[:, :28].sum()),
                fitted_phases=phases.tolist(),
                polarity=polarity.tolist(),
            )
        )
    total = sum(r["evaluation_count"] for r in rows)
    summary = dict(
        rectangles=len(rows),
        rectangle_frames=len(rows) * 78,
        exact_rectangle_frames=sum(r["complete_exact_frames"] for r in rows),
        exact_nonconstant_frames=sum(r["exact_nonconstant_frames"] for r in rows),
        variable_evaluation_decisions=total,
        generator_error_fraction=sum(r["evaluation_errors"] for r in rows) / total,
        majority_error_fraction=sum(r["baseline_errors"] for r in rows) / total,
        windows_generator_better=sum(r["evaluation_errors"] < r["baseline_errors"] for r in rows),
    )
    output = dict(
        summary=summary,
        rows=rows,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (prior_path, source, template_path)
        },
        limitation="Known compact-carrier generator alignment only. Fit phase/polarity "
        "on first28 positions each frame, predict other86. Discovery selects changing "
        "positions; later39frames evaluate. Overlapping windows are not independent "
        "and were selected previously with full reference ranks. Not a BER estimate.",
    )
    (BASE / "local/rectangle_sequence_test.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
