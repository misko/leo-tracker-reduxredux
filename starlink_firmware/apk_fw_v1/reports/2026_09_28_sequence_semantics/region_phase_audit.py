"""Fit the known cyclic vocabulary on one frequency half; check the other."""

import hashlib
import json
from pathlib import Path

import numpy as np
from firmware_seed_search import SEED
from phase_model import codebook
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent
WORDS = np.array(
    [[1 if bit == "1" else -1 for bit in word] for word in codebook(list(map(int, SEED)))],
    dtype=np.int16,
)


def fit_halves(signs, valid, symbol):
    mapping = (np.arange(1004) - 16 * symbol) % 60
    predictions = WORDS[:, mapping]
    observed = signs.astype(np.int16) * valid
    scores = predictions[:, :502] @ observed[:502]
    phase = int(np.argmax(abs(scores)))
    polarity = 1 if scores[phase] >= 0 else -1
    predicted = polarity * predictions[phase]
    support = [int(valid[:502].sum()), int(valid[502:].sum())]
    errors = [
        int(((predicted[:502] != signs[:502]) & valid[:502]).sum()),
        int(((predicted[502:] != signs[502:]) & valid[502:]).sum()),
    ]
    return dict(
        phase=phase,
        polarity=polarity,
        support=support,
        errors=errors,
        error_fraction=[e / n if n else None for e, n in zip(errors, support, strict=True)],
    )


def main():
    source = BASE / "local/full-reference-0-12.npz"
    map_path = BASE / "local/frame_binary_map.json"
    template_path = (
        BASE.parents[3]
        / "docs/research/starlink-literature/local/data/ut-pilots"
        / "supplement/reference-template/referenceTemplate.mat"
    )
    physical = np.array(
        [
            k
            for k in np.argsort(np.fft.fftfreq(1024))
            if 2 <= k < 1022 and k not in range(488, 496) and k not in range(528, 536)
        ]
    )
    archive = np.load(source)
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = archive["symbols"][:, 1:][:, :, physical] * np.exp(-0.5j * np.pi * template[physical, 1:].T)
    quality = (abs(z.imag) < 0.05) & (abs(abs(z.real) - 1) < 0.05)
    rows = []
    for frame in json.loads(map_path.read_text())["frames"]:
        index = frame["frame_index"]
        early, late = frame["binary_like_intervals"]
        selections = [(s, "early") for s in range(early[0], early[1] + 1)]
        selections += [(late[0], "tail_start"), (late[0] + 5, "tail_later")]
        for symbol, region in selections:
            row = fit_halves(
                np.where(z[index, symbol - 2].real >= 0, 1, -1), quality[index, symbol - 2], symbol
            )
            rows.append(dict(frame=index, symbol=symbol, region=region, **row))
    summary = {}
    for region in ("early_common", "early_extension", "tail"):
        selected = [
            r
            for r in rows
            if (region == "early_common" and r["region"] == "early" and r["symbol"] <= 7)
            or (region == "early_extension" and r["region"] == "early" and r["symbol"] > 7)
            or (region == "tail" and r["region"].startswith("tail"))
        ]
        summary[region] = dict(
            symbols=len(selected),
            exact_both=sum(r["errors"] == [0, 0] for r in selected),
            median_error_fraction=np.median(
                [r["error_fraction"] for r in selected], axis=0
            ).tolist(),
        )
    result = dict(
        summary=summary,
        rows=rows,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (source, map_path, template_path)
        },
        limitation="Phase and polarity selected on lower physical frequency half only. "
        "Shared recording/template and exploratory region choice; no protocol semantics "
        "or independent acquisition validation. Tail control samples two symbols/frame.",
    )
    (BASE / "local/region_phase_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
