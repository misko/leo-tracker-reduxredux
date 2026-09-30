"""Independent receiver words and held-region known-pattern subtraction for DS10."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from extend import OUT, PRIOR, sha, write  # noqa: E402

sys.path.insert(0, str(PRIOR))
from decode_tracks import SEED, codebook, slots, word_candidate  # noqa: E402
from state_residuals import assess, fit_gain  # noqa: E402


def main():
    summaries = []
    basis = np.array([[1 if b == "1" else -1 for b in w]
                      for w in codebook(list(map(int, SEED)))])
    for path in sorted((OUT / "paired").glob("*/summary.json")):
        r = json.loads(path.read_text())
        data_path = next(path.parent.glob("*-data-soft.npz"))
        assert hashlib.sha256(data_path.read_bytes()).hexdigest() == r["header"]["sha256"]
        with np.load(data_path) as data:
            bins = data["bins0"]
            assert np.array_equal(bins, data["bins1"])
            a, b = data["z0"], data["z1"]
            words = []
            for f in r["qualified_frames"]:
                left, right = [word_candidate(z[f], bins, f) for z in (a, b)]
                accepted = left["accepted"] and right["accepted"] and left["word"] == right["word"]
                words.append(dict(frame=f, accepted=accepted, left=left, right=right))
            phases = {w["frame"]: w["phase_hypothesis"] for w in r["windows"] if w["label"] == 1}
            frames = sorted(phases)
            residual = None
            if len(frames) >= 8:
                prediction = basis[[phases[f] for f in frames]][:, slots(bins, np.arange(2, 302))]
                x, y = a[frames], b[frames]
                gx, gy = fit_gain(x, prediction), fit_gain(y, prediction)
                residual = [assess(x, y, prediction, gx, gy, start, stop)
                            for start, stop in [(0, 6), (6, 32), (32, 128), (256, 288)]]
            summaries.append(dict(
                name=path.parent.name, source_sha256=sha(path), frames=r["qualified_frames"],
                strict_paired_words=words,
                strict_accepted=sum(w["accepted"] for w in words),
                strict_known=sum(w["accepted"] and w["left"]["known_phase"] is not None
                                 for w in words),
                header=r["header"], residual_frames=len(frames), residual=residual,
            ))
    write(OUT / "paired-summary.json", dict(
        visits=summaries, method_sha256=sha(Path(__file__)),
        limitation="Independent receiver word recovery; no CRC/FEC. Residual assay is "
        "descriptive with >=8 eligible frames and all cyclic mismatch controls preserving "
        "shared-pattern subtraction. Existing changing-header assay retains >=12-frame gate.",
    ))
    for r in summaries:
        print(r["name"], "joint frames", len(r["frames"]), "strict words", r["strict_accepted"],
              "known", r["strict_known"], "header", r["header"].get("matched"),
              "late residual", r["residual"][-1] if r["residual"] else None, flush=True)


if __name__ == "__main__":
    main()
