"""Freeze edge-header copy relations in UT before checking local receiver caches."""

import hashlib
import json
from pathlib import Path

import numpy as np
from decode_tracks import ROOT
from header_copies import select_pairs
from scipy.io import loadmat

BASE = Path(__file__).parent
SOURCE = BASE.parent / "2026_09_28_sequence_semantics/local"


def frozen_pairs(bits, valid, split=39):
    candidates = select_pairs(bits[:split], valid[:split])
    survivors = [
        (a, b, flip)
        for a, b, flip in candidates
        if valid[split:, [a, b]].all() and np.all((bits[split:, a] ^ bits[split:, b]) == flip)
    ]
    return candidates, survivors


def main():
    source = SOURCE / "header-reference-0-77.npz"
    template_path = ROOT / (
        "docs/research/starlink-literature/local/data/ut-pilots/supplement/"
        "reference-template/referenceTemplate.mat"
    )
    template = np.exp(0.5j * np.pi * loadmat(template_path)["referenceTemplateRotations"])
    reference = np.load(source)["symbols"] * template[:, 1:7].T.conj()
    results = []
    for edge, bins in [("upper", np.r_[476:488, 496:508]), ("lower", np.r_[516:528, 536:548])]:
        z = reference[:, :, bins].reshape(78, -1)
        bits = (z.real >= 0).astype(np.uint8)
        valid = (abs(z.imag) < 0.05) & (abs(abs(z.real) - 1) < 0.05)
        pairs, frozen = frozen_pairs(bits, valid)
        rows = []
        for a, b, flip in frozen:
            row = dict(
                symbol_a=a // len(bins) + 2,
                carrier_a=int(bins[a % len(bins)]),
                symbol_b=b // len(bins) + 2,
                carrier_b=int(bins[b % len(bins)]),
                inversion=flip,
                reference_ones=[int(bits[:, a].sum()), int(bits[:, b].sum())],
                transfers=[],
            )
            for name in ["S13", "S22", "S23"] if edge == "upper" else ["DS9-middle", "DS9-last"]:
                path = SOURCE / f"{name}-soft.npz"
                data = np.load(path)
                m = [json.loads(str(data[f"metadata{rx}"])) for rx in range(2)]
                frames = sorted(set(m[0]["evaluation_frames"]) & set(m[1]["evaluation_frames"]))
                frames = [
                    f
                    for f in frames
                    if min(t["diagnostics"][f]["held_pilot_coherence"] for t in m) > 0.5
                ]
                if not frames:
                    continue
                for rx in range(2):
                    ix = {int(k): i for i, k in enumerate(data[f"bins{rx}"])}
                    if row["carrier_a"] not in ix or row["carrier_b"] not in ix:
                        continue
                    values = data[f"z{rx}"]
                    left = values[frames, row["symbol_a"] - 2, ix[row["carrier_a"]]].real >= 0
                    right = values[frames, row["symbol_b"] - 2, ix[row["carrier_b"]]].real >= 0
                    predicted = left ^ bool(flip)
                    p, q = predicted.mean(), right.mean()
                    row["transfers"].append(
                        dict(
                            visit=name,
                            receiver=rx,
                            frames=len(frames),
                            agreement=float(np.mean(predicted == right)),
                            marginal_baseline=float(p * q + (1 - p) * (1 - q)),
                            source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        )
                    )
            rows.append(row)
        results.append(
            dict(
                edge=edge,
                discovery_pairs=len(pairs),
                held_reference_pairs=len(frozen),
                relations=rows,
            )
        )
    out = BASE / "local/reference-copy-transfer"
    out.mkdir(exist_ok=True)
    result = dict(
        method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [source, template_path]
        },
        results=results,
    )
    (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
