"""Fixed-window cross-receiver/cross-frequency audit, preserving within-frame placement."""

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent
ROOT = BASE.parents[1]
OUT = BASE / "local"
sys.path.insert(0, str(BASE.parent / "2026_09_28_signal_clustering"))
sys.path.insert(0, str(BASE.parent / "2026_09_28_ds7_ds8_correspondence"))
from cluster_signals import canonical  # noqa: E402
from native_rate_decode import recover  # noqa: E402
from tcodes import bit_word, fit_code, references, score_code, slots  # noqa: E402

SELECTED = ["S01", "S02", "S06", "S07", "S13", "S18", "S19", "S22", "S23"]


def transformations(word):
    """All mappings from the canonical family to this word, retaining ambiguity."""
    base = canonical(word)
    return [
        (shift, inverse)
        for inverse in [0, 1]
        for shift in range(60)
        if (base.translate(str.maketrans("01", "10")) if inverse else base)[shift:]
        + (base.translate(str.maketrans("01", "10")) if inverse else base)[:shift]
        == word
    ]


def fixed_windows(b0, b1, a, b, frames, threshold):
    results = []
    for frame in frames:
        for first in range(14, 271, 32):
            symbols = np.arange(first, min(first + 32, 301))
            x, y = a[frame, symbols - 2], b[frame, symbols - 2]
            if not np.isfinite(x).all() or not np.isfinite(y).all():
                continue
            m0, m1 = slots(b0, symbols), slots(b1, symbols)
            # Discovery fits all RX0/slice0 samples in this fixed window. No best-window search.
            code, _, c0 = fit_code(x, m0)
            peer, _, c1 = fit_code(y, m1)
            score0, score1 = score_code(x, m0, code), score_code(y, m1, code)
            full = bool(c0.all() and c1.all())
            agreement = bool(full and np.array_equal(code, peer))
            accepted = agreement and min(score0, score1) > threshold
            word = bit_word(code)
            results.append(
                dict(
                    frame=int(frame),
                    first_symbol=first,
                    last_symbol=int(symbols[-1]),
                    accepted=bool(accepted),
                    score0=score0,
                    held=score1,
                    word=word,
                    peer_word=bit_word(peer),
                    full=full,
                    family=canonical(word) if accepted else None,
                    transforms=transformations(word) if accepted else [],
                )
            )
    return results


def summarize(rows):
    accepted = [r for r in rows if r["accepted"]]
    grouped = defaultdict(list)
    for r in accepted:
        grouped[r["frame"]].append(r)
    return dict(
        attempted_windows=len(rows),
        accepted_windows=len(accepted),
        accepted_frames=len(grouped),
        multiple_window_frames=sum(len(r) > 1 for r in grouped.values()),
        conflicting_word_frames=[f for f, r in grouped.items() if len({x["word"] for x in r}) > 1],
        conflicting_family_frames=[
            f for f, r in grouped.items() if len({x["family"] for x in r}) > 1
        ],
        unique_words=len({r["word"] for r in accepted}),
        unique_families=len({r["family"] for r in accepted}),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ut", action="store_true")
    parser.add_argument("--signals", nargs="*", default=[])
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    if args.ut:
        source = BASE.parent / "2026_09_28_ds7_ds8_correspondence/local/ut-codebook"
        archives = [np.load(source / f"bins-{n}.npz") for n in [100, 200]]
        _, template, _ = references()
        bins = [a["bins"] for a in archives]
        z = [a["symbols"][:, 1:] * template[a["bins"], 1:].T.conj() for a in archives]
        rows = fixed_windows(*bins, *z, range(len(z[0])), 0.9)
        result = dict(
            signal="UT",
            results=rows,
            summary=summarize(rows),
            input_sha256={
                str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [source / "bins-100.npz", source / "bins-200.npz"]
            },
        )
        (OUT / "UT-windows.json").write_text(json.dumps(result, indent=2) + "\n")
        print("UT", result["summary"], flush=True)
    inventory = json.loads(
        (BASE.parent / "2026_09_28_signal_clustering/local/inventory.json").read_text()
    )
    for signal in args.signals:
        visit = next(r for r in inventory if r["signal"] == signal)
        assert len(visit["streams"]) == 2
        cache = OUT / f"{signal}-soft.npz"
        binding = hashlib.sha256(json.dumps(visit, sort_keys=True).encode()).hexdigest()
        if cache.exists():
            archive = np.load(cache)
            assert str(archive["binding"]) == binding
            streams = [
                (archive[f"bins{i}"], archive[f"z{i}"], json.loads(str(archive[f"metadata{i}"])))
                for i in [0, 1]
            ]
        else:
            streams = [
                recover(s["row"], Path(s["folder"]), frame_limit=90) for s in visit["streams"]
            ]
            arrays = {"binding": binding}
            for i, (bins, z, meta) in enumerate(streams):
                arrays.update({f"bins{i}": bins, f"z{i}": z, f"metadata{i}": json.dumps(meta)})
            np.savez_compressed(cache, **arrays)
        b0, a, d0 = streams[0]
        b1, b, d1 = streams[1]
        frames = sorted(set(d0["evaluation_frames"]) & set(d1["evaluation_frames"]))
        rows = fixed_windows(b0, b1, a, b, frames, 0.25)
        for row in rows:
            row["strict_pilot"] = (
                row["accepted"]
                and min(d["diagnostics"][row["frame"]]["held_pilot_coherence"] for d in [d0, d1])
                > 0.5
            )
        result = dict(
            signal=signal,
            binding=binding,
            results=rows,
            summary=summarize(rows),
            limitations="Fixed-window exploratory recovery; no shuffled-code gate. "
            "Dual receiver exact equality and correlation gates; "
            "not a replacement for prior qualified word counts.",
        )
        (OUT / f"{signal}-windows.json").write_text(json.dumps(result, indent=2) + "\n")
        print(signal, result["summary"], flush=True)


if __name__ == "__main__":
    main()
