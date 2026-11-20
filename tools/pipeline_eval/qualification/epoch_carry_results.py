"""Score sealed causal forecasts against capture-era pilot timing only."""

import gzip
import json
from collections import Counter, defaultdict, deque

from ..__main__ import save_json
from ..variants import epoch_carry
from . import epoch_carry_trial as trial
from .full_v5_check import BULK, _load_case, _sha

ARMS = ("own", "wrong_channel", "wrong_time")
LIMITS = (0.5, 1, 2, 5, 20, 100, 1000)


def positives(probe):
    return [c for c in probe["candidates"] if c["passed_fractional_margin_gate"]]


def epoch(c):
    return c["integer_epoch_sample"] + c["fractional_epoch_offset_samples"]


def near(observed, predicted, period, require_cfo):
    if predicted is None:
        return None
    distances = [
        abs(epoch_carry.wrap(epoch(c) - predicted["epoch"], period))
        for c in observed
        if not require_cfo
        or abs(
            epoch_carry.wrap(
                c["fractional_tracking_cfo_hz"] - predicted["cfo_hz"],
                epoch_carry.ALIAS_HZ,
            )
        )
        <= 1000
    ]
    return min(distances, default=None)


def missed(teacher, current, period):
    targets = []
    for c in teacher:
        if not any(
            abs(epoch_carry.wrap(epoch(c) - epoch(other), period)) <= 2
            and abs(
                epoch_carry.wrap(
                    c["fractional_tracking_cfo_hz"] - other["fractional_tracking_cfo_hz"],
                    epoch_carry.ALIAS_HZ,
                )
            )
            <= 1000
            for other in current
        ):
            targets.append(c)
    return targets


def bin_name(distance):
    return (
        "no_match"
        if distance is None
        else next((str(limit) for limit in LIMITS if distance <= limit), "above_1000")
    )


def record_group(hist, ident, bucket, predicted, subset, period):
    if not subset:
        return
    hist[ident, "coverage"][bucket + "_with_forecast"] += 1
    for arm in ARMS:
        if predicted[arm] is None:
            continue
        for cfo in (False, True):
            metric = "epoch/cfo" if cfo else "epoch"
            name = bin_name(near(subset, predicted[arm], period, cfo))
            hist[ident, bucket, arm, metric][name] += 1
            if predicted["wrong_channel"] is not None:
                hist[ident, bucket, arm, metric, "common_null"][name] += 1


def score(pin, plan):
    groups = defaultdict(list)
    for line in gzip.decompress((trial.OUT / "predictions.jsonl.gz").read_bytes()).splitlines():
        row = json.loads(line)
        if any(
            p is not None and max(p["prior_samples"]) >= row["sample"]
            for p in (row[a] for a in ARMS)
        ):
            raise ValueError("forecast consumed a current or future capture counter")
        groups[row["id"]].append(row)
    hist, examples = defaultdict(Counter), []
    for authority in plan["cases"]:
        ident = authority["id"]
        case = _load_case(ident)
        path = BULK / case["native"]["path"]
        if _sha(path) != case["native"]["sha256"]:
            raise ValueError("capture-era detector archive changed")
        teacher = json.loads(path.read_bytes())["source"]
        wide = trial.load(authority)["source"]
        anchors = {trial.key(p): p for p in teacher["probes"]}
        period = wide["sample_rate_hz"] / epoch_carry.FRAME_HZ
        assert wide["sample_rate_hz"] == teacher["sample_rate_hz"]
        recurrence = defaultdict(lambda: deque(maxlen=3))
        for probe, p in zip(wide["probes"], groups[ident], strict=True):
            ident_key = tuple(p["key"])
            assert trial.key(probe) == ident_key and probe["valid_start_counter"] == p["sample"]
            cohort = anchors.get(ident_key)
            hist[ident, "coverage"]["processed_probe"] += 1
            current = positives(probe)
            past = recurrence[trial.lane(probe)]
            if (
                len(past) == 3
                and all(ok for _, ok in past)
                and (p["sample"] - past[0][0] <= 1.2 * wide["sample_rate_hz"])
            ):
                hist[ident, "wide_recurrence"]["three_prior_positive"] += 1
                if current:
                    hist[ident, "wide_recurrence"]["three_prior_and_next_positive"] += 1
            past.append((p["sample"], bool(current)))
            if current:
                hist[ident, "coverage"]["current_wide_positive_probe"] += 1
            if p["own"] is not None:
                hist[ident, "coverage"]["forecast_probe"] += 1
                record_group(hist, ident, "current_wide", p, current, period)
            if cohort is None:
                continue
            assert (
                trial.lane(cohort) == tuple(p["lane"])
                and cohort["valid_start_counter"] == p["sample"]
            )
            observed = positives(cohort)
            if not observed:
                continue
            hist[ident, "coverage"]["teacher_positive_probe"] += 1
            if p["own"] is None:
                continue
            hist[ident, "coverage"]["forecast_with_teacher_positive"] += 1
            subsets = {
                "teacher": observed,
                "missed_wide": missed(observed, current, period),
            }
            for bucket, subset in subsets.items():
                if not subset:
                    continue
                record_group(hist, ident, bucket, p, subset, period)
                if bucket == "missed_wide":
                    distance = near(subset, p["own"], period, True)
                    if distance is not None and distance <= 2:
                        examples.append(
                            dict(
                                id=ident,
                                key=p["key"],
                                lane=p["lane"],
                                sample=p["sample"],
                                predicted=p["own"],
                                distance_samples=distance,
                                targets=[
                                    c
                                    for c in subset
                                    if abs(epoch_carry.wrap(epoch(c) - p["own"]["epoch"], period))
                                    <= 2
                                ],
                            )
                        )
    aggregate = defaultdict(Counter)
    for (_, *group), counts in hist.items():
        aggregate["/".join(group)].update(counts)
    save_json(
        trial.OUT / "scores.json",
        dict(
            cases=pin["cases"],
            groups={"/".join(k): v for k, v in hist.items()},
            aggregate=aggregate,
            missed_examples=examples,
        ),
    )


def main():
    pin = json.loads((trial.OUT / "prediction-lock.json").read_bytes())
    for name, digest in pin["files"].items():
        assert _sha(trial.OUT / name) == digest
    data = json.loads((trial.OUT / "plan.json").read_bytes())
    score(pin, data)


if __name__ == "__main__":
    main()
