"""Predict early signs from independently located tail phase; fit no header bits."""

import hashlib
import json
from pathlib import Path

import numpy as np
from region_phase_audit import WORDS

BASE = Path(__file__).parent


def disagreement(bits, predictions, keep):
    return float(np.mean((bits != predictions)[keep])) if keep.any() else None


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
    rows = []
    for tag in ("middle", "last"):
        source = BASE / f"local/DS9-{tag}-soft.npz"
        wp = BASE / (
            "local/ds9_word_audit.json" if tag == "middle" else "local/ds9_last_word_audit.json"
        )
        a = np.load(source)
        assert np.array_equal(a["bins0"], a["bins1"])
        phases = {}
        for r in json.loads(wp.read_text())["rows"]:
            if r["accepted"] and r["phase"] is not None and r["last_symbol"] < 242:
                assert r["frame"] not in phases or phases[r["frame"]] == r["phase"]
                phases[r["frame"]] = r["phase"]
        frames = reliability["per_visit"][tag]["evaluation_frames"]
        values = (a["z0"][frames] + a["z1"][frames]) / 2
        for symbol in [*range(2, 14), 272, 301]:
            slots = (np.array([compact[int(b)] for b in a["bins0"]]) - 16 * symbol) % 60
            predicted = WORDS[np.array([phases[f] for f in frames])[:, None], slots[None]] >= 0
            z = values[:, symbol - 2]
            bits = z.real >= 0
            for gated in (False, True):
                keep = abs(z.real) >= threshold if gated else np.ones(z.shape, bool)
                controls = [
                    disagreement(bits, np.roll(predicted, shift, axis=0), keep)
                    for shift in range(1, len(frames))
                ]
                rows.append(
                    dict(
                        visit=tag,
                        symbol=symbol,
                        gated=gated,
                        count=int(keep.sum()),
                        disagreement=disagreement(bits, predicted, keep),
                        shifted_mean=float(np.mean(controls)),
                        shifted_range=[min(controls), max(controls)],
                    )
                )
        for p in (source, wp):
            hashes[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    output = dict(
        rows=rows,
        input_sha256=hashes,
        limitation="No phase/polarity/header fitting. Earlier accepted paired sequence windows "
        "supply phase, later evaluation frames only. Shift controls descriptive, "
        "not independent trials. Agreement alone cannot identify header fields.",
    )
    (BASE / "local/ds9_header_tail_prediction.json").write_text(json.dumps(output, indent=2) + "\n")
    for row in rows:
        if row["gated"]:
            print(json.dumps(row))


if __name__ == "__main__":
    main()
