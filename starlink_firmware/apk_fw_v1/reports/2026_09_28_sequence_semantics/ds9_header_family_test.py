"""Fit sequence family on disjoint slots, predict unused header slots."""

import hashlib
import json
from pathlib import Path

import numpy as np
from region_phase_audit import WORDS

BASE = Path(__file__).resolve().parent


def predict(values, slots, words):
    candidates = words[:, slots]
    fit = slots < 30
    scores = values[:, fit].real @ candidates[:, fit].T
    phase = np.argmax(abs(scores), axis=1)
    polarity = np.where(scores[np.arange(len(values)), phase] >= 0, 1, -1)
    return polarity[:, None, None] * candidates[phase], phase, polarity


def evaluate(values, prediction, slots, threshold):
    keep = np.broadcast_to(slots >= 30, values.shape) & (abs(values.real) >= threshold)
    return dict(
        count=int(keep.sum()),
        errors=int(((np.sign(values.real) != prediction) & keep).sum()),
        disagreement=float((np.sign(values.real) != prediction)[keep].mean()),
    )


def main():
    physical = [
        int(k)
        for k in np.argsort(np.fft.fftfreq(1024))
        if 2 <= k < 1022 and k not in range(488, 496) and k not in range(528, 536)
    ]
    compact = {b: i for i, b in enumerate(physical)}
    rp = BASE / "local/ds9_combined_reliability.json"
    reliability = json.loads(rp.read_text())
    threshold = reliability["per_visit"]["middle"]["thresholds"]["0.5"]
    hashes = {str(rp): hashlib.sha256(rp.read_bytes()).hexdigest()}
    # Prespecified permutations preserve codebook size and each word's bias.
    rng = np.random.default_rng(20260928)
    controls = [WORDS[:, rng.permutation(60)] for _ in range(20)]
    rows = []
    for tag in ("middle", "last"):
        source = BASE / f"local/DS9-{tag}-soft.npz"
        a = np.load(source)
        assert np.array_equal(a["bins0"], a["bins1"])
        frames = reliability["per_visit"][tag]["evaluation_frames"]
        for region, first in (("header", 2), ("tail_control", 272)):
            values = (
                a["z0"][frames, first - 2 : first + 4] + a["z1"][frames, first - 2 : first + 4]
            ) / 2
            slots = (
                np.array([compact[int(b)] for b in a["bins0"]])[None]
                - 16 * np.arange(first, first + 6)[:, None]
            ) % 60
            prediction, phase, polarity = predict(values, slots, WORDS)
            shuffled = [
                evaluate(values, predict(values, slots, w)[0], slots, threshold) for w in controls
            ]
            rows.append(
                dict(
                    visit=tag,
                    region=region,
                    result=evaluate(values, prediction, slots, threshold),
                    phases=phase.tolist(),
                    polarities=polarity.tolist(),
                    frames=frames,
                    shuffled_codebook_results=shuffled,
                    shuffled_mean=float(np.mean([r["disagreement"] for r in shuffled])),
                )
            )
        hashes[str(source)] = hashlib.sha256(source.read_bytes()).hexdigest()
    output = dict(
        rows=rows,
        input_sha256=hashes,
        limitation="Only slots 0–29 fit phase/polarity per frame; slots 30–59 evaluate. "
        "Six symbols with physical ordering and fixed -16 step; no layout search. "
        "Shuffled codebooks are descriptive controls, not independent trials. "
        "Rejecting this layout does not reject other codes or masks.",
    )
    (BASE / "local/ds9_header_family_test.json").write_text(json.dumps(output, indent=2) + "\n")
    for r in rows:
        print(r["visit"], r["region"], r["result"], "shuffled", r["shuffled_mean"])


if __name__ == "__main__":
    main()
