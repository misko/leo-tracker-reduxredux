"""Recording-aware descriptive summaries for conditional association transfer."""
import math

MODES = ("normal", "reversed", "null")
DIRECTIONS = ("A_to_B", "B_to_A")


def summarize(records):
    if not records:
        return {"tracks": 0, "held_observations": 0, "metrics": None}
    weights = [float(row["weight_seconds"]) for row in records]
    if any(not math.isfinite(w) or w <= 0 for w in weights):
        raise ValueError("invalid track weight")
    for row in records:
        baseline = row["normal"]["baseline_mean_nll"]
        if not isinstance(row["held_count"], int) or row["held_count"] <= 0:
            raise ValueError("invalid held count")
        for mode in MODES:
            value = row[mode]
            a, b, gain = (value[key] for key in ("baseline_mean_nll", "reception_mean_nll",
                                                "improvement_baseline_minus_reception"))
            if (not all(math.isfinite(x) for x in (a, b, gain)) or
                    abs(a - baseline) > 1e-12 or abs(gain - (a-b)) > 1e-12):
                raise ValueError("inconsistent prediction scores")
        if abs(row["null"]["improvement_baseline_minus_reception"]) > 1e-12:
            raise ValueError("candidate-independent control did not cancel")
    total = math.fsum(weights)
    metrics = {}
    for mode in MODES:
        metrics[mode] = {}
        for metric in ("baseline_mean_nll", "reception_mean_nll", "improvement_baseline_minus_reception"):
            values = [row[mode][metric] for row in records]
            metrics[mode][metric] = {
                "equal_track": math.fsum(values)/len(values),
                "occupied_second_weighted": math.fsum(w*v for w,v in zip(weights, values))/total}
    return {"tracks": len(records), "held_observations": sum(r["held_count"] for r in records),
            "weight_seconds": total, "metrics": metrics}


def cohort_summary(records, sessions):
    if len(sessions) != 6 or len(set(sessions)) != 6:
        raise ValueError("expected six unique calibration sessions")
    keys = [(r["session_id"], r["track_id"], r["direction"]) for r in records]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate transfer prediction")
    if any(sid not in sessions or direction not in DIRECTIONS for sid, _, direction in keys):
        raise ValueError("unexpected recording or direction")
    membership = {}
    for sid in sessions:
        halves = [{tid for s,tid,d in keys if s == sid and d == direction} for direction in DIRECTIONS]
        if halves[0] != halves[1]: raise ValueError("incomplete reciprocal predictions")
        membership[sid] = {direction: summarize([r for r in records if r["session_id"] == sid
                                                 and r["direction"] == direction])
                           for direction in DIRECTIONS}
    pooled = {direction: summarize([r for r in records if r["direction"] == direction])
              for direction in DIRECTIONS}
    return {"recordings": membership, "pooled_by_direction": pooled,
            "caveat": "Reciprocal predictions and tracks from a recording are not independent replicates."}
