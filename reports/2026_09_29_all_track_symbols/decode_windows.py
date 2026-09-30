"""Recover candidates across every fixed window of the saved qualified frames."""

import hashlib
import json
from pathlib import Path

import numpy as np
from decode_tracks import SEED, bit_word, codebook, fit_code, slots

BASE = Path(__file__).parent
OUT = BASE / "local"
KNOWN = {word: i for i, word in enumerate(codebook(list(map(int, SEED))))}


def recover_window(values, mapping, seed):
    a, _, ca = fit_code(values[::2], mapping[::2])
    b, _, cb = fit_code(values[1::2], mapping[1::2])
    held = values[1::2]
    held_mapping = mapping[1::2]
    rms = max(float(np.sqrt(np.mean(abs(held) ** 2))), 1e-12)
    sums = np.bincount(held_mapping.ravel(), weights=held.real.ravel(), minlength=60)
    score = float(a @ sums / held.size / rms)
    rng = np.random.default_rng(seed)
    wrong = np.array([rng.permutation(a) for _ in range(99)])
    control = float(np.max(wrong @ sums / held.size / rms))
    full = bool(np.all(ca > 0) and np.all(cb > 0))
    passed = full and np.array_equal(a, b) and score > 0.25 and score > control
    word = bit_word(a)
    nearest = (
        min(
            (sum(x != y for x, y in zip(word, known, strict=True)), phase)
            for known, phase in KNOWN.items()
        )
        if passed
        else (None, None)
    )
    inverted = word.translate(str.maketrans("01", "10"))
    polarity_distance = (
        min(
            nearest[0],
            min(sum(x != y for x, y in zip(inverted, known, strict=True)) for known in KNOWN),
        )
        if passed
        else None
    )
    return dict(
        word=word,
        odd_word=bit_word(b),
        full_coverage=full,
        accepted=bool(passed),
        score=score,
        shuffled_max=control,
        known_phase=KNOWN.get(word) if passed else None,
        nearest_known_hamming=nearest[0],
        nearest_known_phase=nearest[1],
        complement_known_phase=KNOWN.get(inverted) if passed else None,
        nearest_known_hamming_allowing_inversion=polarity_distance,
    )


def main():
    totals = dict(windows=0, accepted=0, known=0, outside_known=0, exact_complements=0)
    source_bindings = {}
    method_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for receipt in sorted((OUT / "decoded").glob("*/results.json")):
        source_bindings[str(receipt)] = hashlib.sha256(receipt.read_bytes()).hexdigest()
        cached = receipt.parent / "windows.json"
        if cached.exists():
            previous = json.loads(cached.read_text())
            if (
                previous.get("method_sha256") == method_sha
                and previous["source_sha256"] == source_bindings[str(receipt)]
            ):
                for k in totals:
                    totals[k] += previous["counts"][k]
                continue
        result = json.loads(receipt.read_text())
        before = totals.copy()
        rows = []
        for track in result["rows"]:
            windows = []
            if track.get("qualified_frames"):
                path = Path(track["artifact"])
                assert hashlib.sha256(path.read_bytes()).hexdigest() == track["artifact_sha256"]
                d = np.load(path)
                all_z = d["z"]
                bins = d["bins"]
                keep = ~np.isin(bins, track["receiver_metadata"]["pilot_bins"])
                bins = bins[keep]
                for frame in track["qualified_frames"]:
                    for start in range(2, 302, 32):
                        stop = min(start + 32, 302)
                        values = all_z[frame, start - 2 : stop - 2][:, keep]
                        r = recover_window(
                            values, slots(bins, np.arange(start, stop)), seed=194 * frame + start
                        )
                        windows.append(
                            dict(frame=frame, first_symbol=start, last_symbol=stop - 1, **r)
                        )
                        totals["windows"] += 1
                        totals["accepted"] += r["accepted"]
                        totals["known"] += r["known_phase"] is not None
                        totals["outside_known"] += r["accepted"] and r["known_phase"] is None
                        totals["exact_complements"] += r["complement_known_phase"] is not None
            rows.append(dict(index=track["index"], track_id=track["track_id"], windows=windows))
        (receipt.parent / "windows.json").write_text(
            json.dumps(
                dict(
                    source_sha256=source_bindings[str(receipt)],
                    method_sha256=method_sha,
                    counts={k: totals[k] - before[k] for k in totals},
                    rows=rows,
                ),
                indent=2,
            )
            + "\n"
        )
    (OUT / "window_summary.json").write_text(
        json.dumps(
            dict(
                counts=totals,
                source_bindings=source_bindings,
                limitation="Ten nonoverlapping fixed windows per pilot-qualified evaluation frame. "
                "Single receiver even/odd checks. No FEC; adjacent symbols/windows are dependent. "
                "no multiple-comparison significance claim. Last window is shorter.",
            ),
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(totals), flush=True)


if __name__ == "__main__":
    main()
