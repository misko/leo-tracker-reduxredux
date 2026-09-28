"""Localize tail model errors, selecting problematic carriers on discovery only."""

import hashlib
import json
from pathlib import Path

import numpy as np
from boundary_tail_prediction import predicted_signs
from scipy.io import loadmat

BASE = Path(__file__).parent


def select_exceptions(errors, support, split=6, threshold=0.1):
    rates = errors[:split].sum(axis=0) / np.maximum(support[:split].sum(axis=0), 1)
    return rates > threshold


def main():
    source = BASE / "local/full-soft-reference-0-12.npz"
    boundary_path = BASE / "local/soft_tail_boundary.json"
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
    z = np.load(source)["symbols"][:, 1:][:, :, bins] * np.exp(-0.5j * np.pi * template[bins, 1:].T)
    boundaries = [
        r["boundary"] for r in json.loads(boundary_path.read_text())["rows"] if r["flank"] == 502
    ]
    errors, support = [], []
    for frame, boundary in enumerate(boundaries):
        positions = np.arange(boundary, 301200)
        values = z[frame].ravel()[boundary:]
        valid = np.isfinite(values)
        wrong = ((values.real >= 0) != (predicted_signs(boundary, positions) >= 0)) & valid
        errors.append(np.bincount(positions[wrong] % 1004, minlength=1004))
        support.append(np.bincount(positions[valid] % 1004, minlength=1004))
    errors, support = np.array(errors), np.array(support)
    selected = select_exceptions(errors, support)
    summary = []
    for name, frames in (("discovery", slice(0, 6)), ("evaluation", slice(6, 13))):
        for region, mask in (("selected_carriers", selected), ("other_carriers", ~selected)):
            summary.append(
                dict(
                    split=name,
                    region=region,
                    decisions=int(support[frames][:, mask].sum()),
                    errors=int(errors[frames][:, mask].sum()),
                )
            )
    result = dict(
        summary=summary,
        selected_bins=bins[selected].tolist(),
        selection="Discovery frames0..5 carrier error fraction >0.1; evaluation6..12",
        bins=bins.tolist(),
        errors=errors.tolist(),
        support=support.tolist(),
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (source, boundary_path, template_path)
        },
        limitation="Posthoc localization followed by a fixed discovery-only carrier "
        "gate; not a new acquisition or pre-registered validation. Exception is "
        "retained in results, not silently removed or declared noise. Unknown "
        "cause; no additional semantic bits recovered.",
    )
    (BASE / "local/tail_error_localization.json").write_text(json.dumps(result, indent=2) + "\n")
    print("selected", result["selected_bins"])
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
