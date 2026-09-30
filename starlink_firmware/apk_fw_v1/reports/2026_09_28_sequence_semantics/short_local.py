"""Eight-symbol independent-receiver recovery using existing DS7/DS8 caches."""

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from window_audit import bit_word, fit_code, score_code, slots

BASE = Path(__file__).resolve().parent
OUT = BASE / "local"


def recover_pair(a, b, m0, m1, threshold=0.25):
    code, _, count = fit_code(a, m0)
    peer, _, count_peer = fit_code(b, m1)
    if not (count.all() and count_peer.all() and np.array_equal(code, peer)):
        return None
    scores = [score_code(a, m0, code), score_code(b, m1, code)]
    if min(scores) <= threshold:
        return None
    return dict(word=bit_word(code), scores=scores)


def main():
    model = json.loads((OUT / "phase_model.json").read_text())
    lookup = {word: k for k, word in enumerate(model["generated_words"])}
    with (OUT / "phase_indices.csv").open() as stream:
        original = {(r["signal"], int(r["frame"])): r["word"] for r in csv.DictReader(stream)}
    rng = np.random.default_rng(8028)
    accepted, controls, summaries = [], [], []
    hashes = {}
    for path in sorted(OUT.glob("S*-soft.npz")):
        p = np.load(path)
        signal = path.stem.split("-")[0]
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        a, b, b0, b1 = p["z0"], p["z1"], p["bins0"], p["bins1"]
        meta = [json.loads(str(p[f"metadata{i}"])) for i in [0, 1]]
        frames = sorted(set(meta[0]["evaluation_frames"]) & set(meta[1]["evaluation_frames"]))
        old = json.loads((OUT / f"{signal}-windows.json").read_text())["results"]
        old_frames = {r["frame"] for r in old if r["accepted"]}
        attempted = 0
        for frame in frames:
            for first in range(14, 295, 8):
                symbols = np.arange(first, first + 8)
                x, y = a[frame, symbols - 2], b[frame, symbols - 2]
                if not (np.isfinite(x).all() and np.isfinite(y).all()):
                    continue
                attempted += 1
                m0, m1 = slots(b0, symbols), slots(b1, symbols)
                found = recover_pair(x, y, m0, m1)
                if found is None:
                    continue
                code = np.array([1 if v == "1" else -1 for v in found["word"]])
                shuffled = [score_code(y, m1, rng.permutation(code)) for _ in range(999)]
                pvalue = (1 + sum(s >= found["scores"][1] for s in shuffled)) / 1000
                pilot = min(m["diagnostics"][frame]["held_pilot_coherence"] for m in meta)
                strict = min(found["scores"]) > 0.5 and pilot > 0.5 and pvalue <= 0.001
                row = dict(
                    signal=signal,
                    frame=frame,
                    first_symbol=first,
                    **found,
                    phase_index=lookup.get(found["word"]),
                    pilot=float(pilot),
                    shuffle_p=pvalue,
                    strict=bool(strict),
                    new_vs_original=(signal, frame) not in original,
                    new_vs_32=frame not in old_frames,
                    agrees_original=original.get((signal, frame), found["word"]) == found["word"],
                )
                accepted.append(row)
                # Same samples, deliberately permuted carrier-to-slot mapping.
                wrong = recover_pair(x, y, m0[:, ::-1], m1[:, ::-1])
                if wrong:
                    controls.append(
                        dict(
                            signal=signal,
                            frame=frame,
                            first_symbol=first,
                            generator_match=wrong["word"] in lookup,
                        )
                    )
        rows = [r for r in accepted if r["signal"] == signal]
        summaries.append(
            dict(
                signal=signal,
                attempts=attempted,
                accepted=len(rows),
                strict=sum(r["strict"] for r in rows),
                generator_matches=sum(r["phase_index"] is not None for r in rows),
                new_strict_frames_vs_both=sorted(
                    {
                        r["frame"]
                        for r in rows
                        if r["strict"]
                        and r["new_vs_original"]
                        and r["new_vs_32"]
                        and r["phase_index"] is not None
                    }
                ),
            )
        )
        print(summaries[-1], flush=True)
    result = dict(
        summaries=summaries,
        accepted=accepted,
        wrong_mapping_controls=controls,
        input_sha256=hashes,
        limitations="Exploratory eight-symbol assay, not replacement for original "
        "907 observations. Fitting is independent per receiver, no nearest-word "
        "correction. Shuffle gates are unadjusted and overlapping windows are dependent. "
        "Wrong mapping controls run on accepted candidates only.",
    )
    (OUT / "short_local.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
