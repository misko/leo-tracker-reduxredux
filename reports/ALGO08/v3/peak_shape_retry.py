"""Rank short positives by spectral curvature and competing-peak power."""

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from math import ceil, isfinite, sqrt
from pathlib import Path
from statistics import variance


HERE = Path(__file__).resolve().parent
TRACE = "5ff3bb04368a461979a2840074e37164b82bce78d8eb1d12c68e407f565da39d"
LABELS = "2c3e0f045a02755376992ab691ebc0583729459a340f291590a6f740d6ea64f5"


def archived(name, digest):
    blob = (HERE / "measurements" / f"split-spectrum-{name}.json.gz").read_bytes()
    if sha256(blob).hexdigest() != digest:
        raise ValueError("Archived input differs from enrollment")
    return json.loads(gzip.decompress(blob))


def confidence(metric):
    halves = (metric or {}).get("exact", ())
    if len(halves) != 2 or any(peak is None for peak in halves):
        return 0.0
    values = []
    for peak in halves:
        power = peak["score"]
        curvature = peak["curvature"]
        rival = peak["distinct_peak"] or 0.0
        if curvature is None or not all(map(isfinite, (power, rival, curvature))):
            return 0.0
        if power <= 0 or curvature >= 0:
            return 0.0
        if not 0 <= rival <= power:
            raise ValueError("Separated local maximum exceeds the global peak")
        values.append(-curvature * (1.0 - rival / power))
    return min(values)


def predictions(groups):
    rows = {cohort: [dict(key=r["key"], lane=r["lane"], digest=r["digest"],
                          confidence=confidence(r["metric"])) for r in group if r["factor"] is not None]
            for cohort, group in groups.items()}
    train = sorted(r["confidence"] for r in rows["dense"])
    if not train:
        raise ValueError("No dense positives for the frozen cutoff")
    cutoff = train[ceil(len(train) / 4) - 1]
    for group in rows.values():
        for row in group:
            row["retry"] = row["confidence"] <= cutoff
    return dict(trace_sha256=TRACE, cutoff=cutoff, rows=rows)


def compare(predicted, reference):
    positives = [r for r in reference if r["state"] != "short_empty"]
    by_lane = {(r["key"], r["lane"]): r for r in positives}
    keys = [(r["key"], r["lane"]) for r in predicted]
    if len(keys) != len(set(keys)) or len(by_lane) != len(positives) or set(keys) != set(by_lane):
        raise ValueError("Prediction and signed reference have different positive lanes")
    spent = Counter()
    states = Counter()
    squared_errors = []
    captured = total = 0.0
    for proposal, key in zip(predicted, keys, strict=True):
        row = by_lane[key]
        state = row["state"]
        states[state] += 1
        if proposal["retry"]:
            spent[state] += 1
        squared = row["error_hz"] ** 2 if state == "matched" else 0.0
        squared_errors.append(squared)
        total += squared
        if proposal["retry"]:
            captured += squared
    if not states["matched"] or total <= 0:
        raise ValueError("No nonzero same-signal discrepancy to recover")
    fraction = spent.total() / states.total()
    matched = states["matched"]
    # Simple random sampling of a fixed count without replacement.
    sample_sum_variance = (spent.total() * (1 - fraction) * variance(squared_errors)
                           if len(squared_errors) > 1 else 0.0)
    return dict(positive_count=states.total(), states=states, paid=spent.total(), paid_states=spent,
                selected_fraction=fraction, captured_squared_fraction=captured / total,
                uniform_squared_fraction_sd=sqrt(sample_sum_variance) / total,
                uniform_expected_squared_fraction=fraction, original_rms_hz=sqrt(total / matched),
                best_possible_rms_hz=sqrt((total - captured) / matched),
                sqrt_uniform_expected_mse_hz=sqrt(total * (1 - fraction) / matched))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("predict", "score"))
    cli.add_argument("predictions", type=Path)
    args = cli.parse_args()
    frozen = predictions(archived("trace", TRACE)["data"])
    if args.mode == "predict":
        with args.predictions.open("x") as out:
            json.dump(frozen, out, sort_keys=True, allow_nan=False)
        return
    seal = args.predictions.read_bytes()
    if json.loads(seal) != frozen:
        raise ValueError("Short-side predictions changed")
    labels = archived("score", LABELS)
    if labels["trace_sha256"] != TRACE:
        raise ValueError("Labels refer to a different source trace")
    result = {k: compare(v, labels["rows"][k]) for k, v in frozen["rows"].items()}
    print(json.dumps(dict(cutoff=frozen["cutoff"], predictions_sha256=sha256(seal).hexdigest(),
                          labels_sha256=LABELS, trace_sha256=TRACE, cohorts=result), indent=2))


if __name__ == "__main__":
    main()
