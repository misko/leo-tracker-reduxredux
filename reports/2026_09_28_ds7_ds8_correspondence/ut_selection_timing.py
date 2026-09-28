"""Bounded periodic pattern-selection model with whole-time-block evaluation."""

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE.parent / "2026_09_27_ds7_header"))
from code_model_audit import binary_rank  # noqa: E402


def mode(values):
    return min(Counter(values).items(), key=lambda pair: (-pair[1], pair[0]))[0]


def predict(train, test, period):
    baseline = mode([r["label"] for r in train])
    phases = defaultdict(list)
    for row in train:
        phases[row["tick"] % period].append(row["label"])
    mapping = {phase: mode(labels) for phase, labels in phases.items()}
    return [mapping.get(row["tick"] % period, baseline) for row in test]


def main():
    catalogue = BASE / "local/ut-codebook/comparison.json"
    metadata = BASE / "local/ut-codebook/timing-metadata.npz"
    provenance = json.loads(metadata.with_suffix(".json").read_text())
    assert hashlib.sha256(metadata.read_bytes()).hexdigest() == provenance["sha256"]
    reference = json.loads((metadata.parent / "bins-100.json").read_text())
    assert reference["etag"] == provenance["etag"]
    codes = json.loads(catalogue.read_text())["accepted"]
    times = np.load(metadata)["TOAs"].ravel()
    gaps = np.diff(times) * 750
    boundaries = np.flatnonzero(abs(gaps - np.rint(gaps)) > 0.05) + 1
    segments = np.split(np.arange(len(times)), boundaries)
    segment = max(segments, key=len)
    ticks = np.rint((times - times[segment[0]]) * 750).astype(int)
    residual = (times - times[segment[0]]) * 750 - ticks
    assert np.max(abs(residual[segment])) < 0.05
    selected = [r for r in codes if r["frame"] in set(segment.tolist())]
    blocks = {r["frame"]: int((times[r["frame"]] - times[segment[0]]) / 0.2) for r in selected}
    unique_blocks = np.array(sorted(set(blocks.values())))
    shuffled = np.random.default_rng(20260930).permutation(unique_blocks)
    train_blocks = set(shuffled[: round(0.6 * len(shuffled))].tolist())
    results = []
    for field in ["word", "family"]:
        rows = [
            dict(tick=int(ticks[r["frame"]]), block=blocks[r["frame"]], label=r[field])
            for r in selected
        ]
        train = [r for r in rows if r["block"] in train_blocks]
        test = [r for r in rows if r["block"] not in train_blocks]
        trials = []
        for period in range(2, 129):
            hits = total = 0
            for block in sorted(train_blocks):
                fit = [r for r in train if r["block"] != block]
                validation = [r for r in train if r["block"] == block]
                predictions = predict(fit, validation, period)
                hits += sum(p == r["label"] for p, r in zip(predictions, validation, strict=True))
                total += len(validation)
            trials.append(dict(period=period, correct=hits, total=total))
        best = max(trials, key=lambda r: r["correct"])
        predictions = predict(train, test, best["period"])
        baseline = mode([r["label"] for r in train])
        results.append(
            dict(
                field=field,
                selected=best,
                train_observations=len(train),
                evaluation_observations=len(test),
                evaluation_correct=sum(
                    p == r["label"] for p, r in zip(predictions, test, strict=True)
                ),
                baseline_correct=sum(r["label"] == baseline for r in test),
                trials=trials,
            )
        )
    words = np.array([[int(bit) for bit in r["word"]] for r in codes], dtype=np.uint8)
    output = dict(
        input_sha256={
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [catalogue, metadata]
        },
        binary_linear_rank=binary_rank(words),
        parity_odd_rows=int((words.sum(axis=1) % 2).sum()),
        discontinuity_count=len(boundaries),
        segment_first=int(segment[0]),
        segment_last=int(segment[-1]),
        max_tick_residual=float(max(abs(residual[segment]))),
        train_blocks=sorted(train_blocks),
        evaluation_blocks=sorted(set(unique_blocks.tolist()) - train_blocks),
        results=results,
        scope="Longest continuous arrival-time segment; modulo-frame lookup periods 2..128, "
        "selected by leave-one-time-block-out training accuracy. Separate 200 ms blocks "
        "reserved for evaluation. Prior catalogue inspection makes this exploratory.",
        limitations="Receiver-relative arrival times, not decoded UTC. No general exclusion "
        "of timing/state dependence, arbitrary nonperiodic mappings or longer periods.",
    )
    (BASE / "local/ut-codebook/selection-timing.json").write_text(
        json.dumps(output, indent=2) + "\n"
    )
    print(
        json.dumps(
            {**output, "results": [{k: v for k, v in r.items() if k != "trials"} for r in results]},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
