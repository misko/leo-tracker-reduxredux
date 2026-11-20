"""Score endpoints against a fixed recording roster and its original reference outputs."""

import math
from collections import Counter, defaultdict
from statistics import mean

ARMS = ("c0", "fitted_c")
ROLES = ("baseline", "selective-gap", "omitted-track-one", "omitted-tracks")
POSITION_FAILURES = frozenset({"failed", "timed_out", "unavailable", "missing"})
NUMERICAL_TOLERANCE_KM = 0.001


def distribution(values):
    ordered = sorted(v for v in values if v is not None)

    def percentile(p):
        index = (len(ordered) - 1) * p
        lo = math.floor(index)
        return ordered[lo] + (index - lo) * (ordered[math.ceil(index)] - ordered[lo])

    return {
        "n": len(ordered),
        "mean": mean(ordered) if ordered else None,
        **{
            k: percentile(p) if ordered else None
            for k, p in [
                ("min", 0),
                ("p10", 0.1),
                ("p25", 0.25),
                ("p50", 0.5),
                ("p75", 0.75),
                ("p90", 0.9),
                ("p95", 0.95),
                ("p99", 0.99),
                ("max", 1),
            ]
        },
    }


def coordinate(value):
    if value is None:
        return None
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("coordinate must contain latitude and longitude")
    if any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
        for v in value
    ):
        raise ValueError("coordinate must contain finite numbers")
    if abs(value[0]) > 90 or abs(value[1]) > 180:
        raise ValueError("coordinate outside latitude/longitude range")
    return value


def distance_km(a, b):
    if a is None or b is None:
        return None
    lat, lon = map(math.radians, coordinate(a))
    other_lat, other_lon = map(math.radians, coordinate(b))
    chord = (
        math.sin((other_lat - lat) / 2) ** 2
        + math.cos(lat) * math.cos(other_lat) * math.sin((other_lon - lon) / 2) ** 2
    )
    return 12742.0176 * math.asin(math.sqrt(min(1.0, chord)))


def terminal_position_decision(result):
    metrics = result.get("metrics", {})
    return (
        metrics.get("terminal_position_decision") is True
        and metrics.get("position_attempted") is False
        and result.get("status") == "withheld"
    )


def arm_outcome(result, endpoint):
    if endpoint.get("status") == "unavailable":
        return "unavailable", endpoint.get("reason")
    return result.get("status", "missing"), result.get("reason")


def validate_result(result):
    if not isinstance(result, dict) or result.get("status") not in POSITION_FAILURES | {
        "ok",
        "withheld",
    }:
        raise ValueError("unknown prediction status")
    if not result.get("boundary") or not isinstance(result.get("metrics"), dict):
        raise ValueError("a result needs its measured boundary and metrics")
    if result["status"] != "ok" and not result.get("reason"):
        raise ValueError("a non-successful result needs a reason")
    marker = result["metrics"].get("terminal_position_decision", False)
    if not isinstance(marker, bool):
        raise ValueError("terminal position decision marker must be boolean")
    if marker and (
        not terminal_position_decision(result)
        or "arms" not in result
        or not isinstance(result["reason"], str)
        or not result["reason"].strip()
    ):
        raise ValueError("terminal position decision needs an unrefined withholding in both arms")
    if "arms" not in result:
        return
    arms = result["arms"]
    if not isinstance(arms, dict) or set(arms) != set(ARMS):
        raise ValueError("a position experiment must report both calibration arms")
    for arm in arms.values():
        if "latlon" not in arm:
            raise ValueError("a position arm must declare latlon")
        point = coordinate(arm["latlon"])
        forced = coordinate(arm.get("forced_latlon"))
        if point is not None and result["status"] != "ok":
            raise ValueError("a withheld or failed result cannot publish a coordinate")
        if marker and forced is not None:
            raise ValueError("a terminal position decision cannot supply a forced coordinate")
        rms = arm.get("rf_rms_hz")
        if arm.get("status") == "unavailable" and (
            any(value is not None for value in (point, forced, rms))
            or not isinstance(arm.get("reason"), str)
            or not arm["reason"].strip()
        ):
            raise ValueError("an unavailable calibration arm needs a reason and no fitted values")
        if rms is not None and (not math.isfinite(rms) or rms < 0):
            raise ValueError("invalid frequency RMS")
    if result["status"] == "ok" and not any(a["latlon"] is not None for a in arms.values()):
        raise ValueError("a successful positioning result must publish a coordinate")


def thresholds(errors):
    return {str(k): sum(e is not None and e <= k for e in errors) for k in (1, 2, 5, 10)}


def baseline_rows(refs):
    rows = defaultdict(list)
    for case in refs:
        for method, arms in case["reference"].items():
            for arm, a in arms.items():
                key = (case["group"], case["condition"], method, arm)
                rows[key].append(a.get("error_km"))
    return [
        dict(
            group=g,
            condition=c,
            method=m,
            arm=a,
            attempts=len(e),
            error_km=distribution(e),
            within_km=thresholds(e),
        )
        for (g, c, m, a), e in sorted(rows.items())
    ]


def _reference(case, role, arm):
    group = case["reference"].get(role, {})
    return group.get(arm, group.get("shape", {}))


def score(refs, predictions):
    expected = {case["id"] for case in refs}
    if len(expected) != len(refs):
        raise ValueError("duplicate ID in reference roster")
    if extra := predictions.keys() - expected:
        raise ValueError(f"prediction ID outside the selected panel: {sorted(extra)[0]}")
    rows, statuses, metrics, wall = [], Counter(), [], []
    for case in refs:
        record = predictions.get(case["id"], {})
        result = record.get(
            "result",
            {
                "status": "missing",
                "reason": "no submitted prediction",
                "boundary": "unreported",
                "metrics": {},
            },
        )
        validate_result(result)
        statuses[result["status"]] += 1
        metrics.append(result["metrics"])
        if record.get("worker_wall_s") is not None:
            wall.append(record["worker_wall_s"])
        for arm in ARMS:
            a = (result.get("arms") or {}).get(arm, {})
            status, reason = arm_outcome(result, a)
            error = distance_km(a.get("latlon"), case["truth"])
            reference = _reference(case, "baseline", arm)
            grid = _reference(case, "grid_one", arm) or _reference(case, "grid_four", arm)
            rows.append(
                dict(
                    id=case["id"],
                    recording=case["recording"],
                    group=case["group"],
                    condition=case["condition"],
                    arm=arm,
                    status=status,
                    position_method="arms" in result,
                    reason=reason,
                    error_km=error,
                    forced_error_km=distance_km(a.get("forced_latlon"), case["truth"]),
                    rf_rms_hz=a.get("rf_rms_hz"),
                    v5_scored=bool(reference),
                    grid_scored=bool(grid),
                    v5_error_km=reference.get("error_km"),
                    grid_error_km=grid.get("error_km"),
                    v5_coordinate_delta_km=distance_km(a.get("latlon"), reference.get("latlon")),
                    grid_coordinate_delta_km=distance_km(a.get("latlon"), grid.get("latlon")),
                    historical_v5_wall_s=reference.get("wall_s"),
                )
            )
    groups = defaultdict(list)
    for row in rows:
        groups[row["group"], row["condition"], row["arm"]].append(row)
    summaries = [score_group(*key, entries) for key, entries in sorted(groups.items())]
    same_work = [
        (m["control_s"], m["candidate_s"])
        for m in metrics
        if all(
            isinstance(m.get(k), (int, float)) and math.isfinite(m[k]) and m[k] > 0
            for k in ("control_s", "candidate_s")
        )
    ]
    timing = dict(
        worker_wall_s=distribution(wall),
        matched_cases=len(same_work),
        control_s=distribution(a for a, _ in same_work),
        candidate_s=distribution(b for _, b in same_work),
        paired_ratio_control_over_candidate=distribution(a / b for a, b in same_work),
    )
    return dict(
        attempts=len(refs), statuses=dict(sorted(statuses.items())), groups=summaries, timing=timing
    ), rows


def score_group(group, condition, arm, rows):
    errors = [r["error_km"] for r in rows]
    ref = [r["v5_error_km"] for r in rows]
    est, baseline = distribution(errors), distribution(ref)
    paired = [(a, b) for a, b in zip(errors, ref, strict=True) if a is not None and b is not None]
    decisions = Counter()
    for row in rows:
        if row["error_km"] is not None:
            decisions["published"] += 1
        elif not row["position_method"] and row["status"] in ("ok", "withheld"):
            decisions["stage_only"] += 1
        elif row["status"] == "ok":
            decisions["withheld"] += 1
        else:
            decisions[row["status"]] += 1
    within, ref_within = thresholds(errors), thresholds(ref)
    lost = sum(a is None and b is not None for a, b in zip(errors, ref, strict=True))
    checks = None
    if (
        condition == "present"
        and all(r["v5_scored"] for r in rows)
        and baseline["n"]
        and any(r["position_method"] for r in rows)
    ):
        same_coordinates = all(
            (r["error_km"] is None and r["v5_error_km"] is None)
            or (
                r["v5_coordinate_delta_km"] is not None
                and r["v5_coordinate_delta_km"] <= NUMERICAL_TOLERANCE_KM
            )
            for r in rows
        )
        tolerance = NUMERICAL_TOLERANCE_KM if same_coordinates else 0.0
        checks = dict(
            coverage=est["n"] >= baseline["n"], within_5_km=within["5"] >= ref_within["5"]
        )
        for k in ("p50", "p95", "max"):
            checks[k] = est[k] is not None and est[k] <= baseline[k] + tolerance
    return dict(
        group=group,
        condition=condition,
        arm=arm,
        attempts=len(rows),
        error_km=est,
        decision_counts=dict(sorted(decisions.items())),
        within_km=within,
        forced_error_km=distribution(r["forced_error_km"] for r in rows),
        false_publications=est["n"] if condition == "missing" else None,
        rf_rms_hz=distribution(r["rf_rms_hz"] for r in rows),
        v5_error_km=baseline,
        v5_within_km=ref_within,
        lost_v5_fixes=lost,
        v5_paired_change_km=distribution(a - b for a, b in paired),
        v5_coordinate_delta_km=distribution(r["v5_coordinate_delta_km"] for r in rows),
        grid_coordinate_delta_km=distribution(r["grid_coordinate_delta_km"] for r in rows),
        grid_error_km=distribution(r["grid_error_km"] for r in rows),
        checks=checks,
        keeps_v5_panel=all(checks.values()) if checks else None,
    )
