"""Audit raw-excerpt labels against published array indices and header decisions."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]


def compare(raw, reference):
    valid = np.isfinite(reference) & (abs(reference.imag) < 0.05)
    valid &= abs(abs(reference.real) - 1) < 0.05
    matches = (raw.real >= 0) == (reference.real >= 0)
    return dict(decisions=int(valid.sum()), matches=int((matches & valid).sum()))


def main():
    path = BASE / "local/pilot_polarity.npz"
    archive = np.load(path)
    source = (BASE.parents[3] / "reports") / "2026_09_28_ds7_ds8_correspondence/local/ut-codebook"
    templatepath = (
        ROOT
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement/reference-template"
        / "referenceTemplate.mat"
    )
    template = np.exp(0.5j * np.pi * loadmat(templatepath)["referenceTemplateRotations"])
    pieces, bins, inputs = [], [], [path, templatepath]
    for first in [100, 200]:
        p = source / f"bins-{first}.npz"
        inputs.append(p)
        a = np.load(p)
        pieces.append(a["symbols"][:, 1:] * template[a["bins"], 1:].T.conj())
        bins.extend(a["bins"].tolist())
    reference = np.concatenate(pieces, axis=-1)
    indices = [archive["bins"].tolist().index(b) for b in bins]
    raw = archive["deviations"][:, 0][:, :, indices]
    candidates = []
    for offset in range(-2, 3):
        ref_indices = np.arange(250, 257) + offset
        candidates.append(
            dict(
                offset=offset,
                discovery=compare(raw[:3, :6], reference[ref_indices[:3], :6]),
                evaluation=compare(raw[3:, :6], reference[ref_indices[3:], :6]),
            )
        )
    best = max(candidates, key=lambda r: r["discovery"]["matches"] / r["discovery"]["decisions"])
    tails = [
        dict(
            raw_frame_label=f + 250,
            reference_array_index=f + 250 + best["offset"],
            symbol=s,
            **compare(raw[f, s - 2], reference[f + 250 + best["offset"], s - 2]),
        )
        for f, s in [(0, 301), (4, 300), (4, 301), (5, 300), (5, 301)]
    ]
    result = dict(
        selected_by_discovery=best,
        offset_candidates=candidates,
        tails=tails,
        input_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        scope="Eight cached carriers; raw labels 250..256 versus zero-based reference "
        "indices. Discovery uses first three frames; final four verify the offset. "
        "Header signs cover OFDM 2..7. Tail signs are checked separately.",
        limitations="Same underlying RF and published template; different processing "
        "pipelines, not independent RF samples. Agreement is not a CRC or semantic decode.",
    )
    (BASE / "local/reference_agreement.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(selected=best, tails=tails), indent=2))


if __name__ == "__main__":
    main()
