"""Causal, hard-budget reuse of archived capture-era detector visits."""

from math import isfinite

MARGIN = 0.025
ALIAS = 1 / 4.4e-6
EPOCHS = 13_333
BUDGETS = (128, 16)


def visit_pairs(probes):
    previous = -1
    rows = iter(probes)
    for first in rows:
        second = next(rows, None)
        visit = first["visit_index"]
        if (
            second is None
            or visit <= previous
            or second["visit_index"] != visit
            or (first["receiver_id"], second["receiver_id"]) != (0, 1)
        ):
            raise ValueError("expected strictly ordered, complete physical stereo visits")
        previous = visit
        yield visit, (first, second)


def wrapped(value, period):
    return (value + period / 2) % period - period / 2


def distinct(a, b):
    phase_a, phase_b = (
        c["integer_epoch_sample"] + c["fractional_epoch_offset_samples"] for c in (a, b)
    )
    difference_hz = a["fractional_tracking_cfo_hz"] - b["fractional_tracking_cfo_hz"]
    return abs(wrapped(phase_a - phase_b, EPOCHS)) > 2 or abs(wrapped(difference_hz, ALIAS)) > 1000


def trigger(pair):
    for probe in pair:
        candidates = sorted(
            probe["candidates"], key=lambda c: (-c["fractional_margin"], c["candidate_rank"])
        )
        if any(
            not isfinite(c["fractional_margin"])
            or c["passed_fractional_margin_gate"] != (c["fractional_margin"] >= MARGIN)
            for c in candidates
        ):
            raise ValueError("probe does not follow the frozen margin gate")
        if not candidates:
            continue
        best, *alternatives = candidates
        margin = best["fractional_margin"]
        if MARGIN / 2 <= margin < MARGIN:
            return dict(reason="near_gate", rx=probe["receiver_id"], margin=margin)
        for alternative in alternatives:
            alternate = alternative["fractional_margin"]
            if alternate < MARGIN or margin - alternate > MARGIN / 4:
                break
            if distinct(best, alternative):
                return dict(
                    reason="competing_branch",
                    rx=probe["receiver_id"],
                    margin=margin,
                    alternative_margin=alternate,
                )
    return None


def schedule(probes):
    """Rank and spend from only the current/earlier admitted wide visits."""
    ids, reasons, selected = [], {}, {b: [] for b in BUDGETS}
    spent = dict.fromkeys(BUDGETS, 0)
    for i, (visit, pair) in enumerate(visit_pairs(probes)):
        ids.append(visit)
        if not (reason := trigger(pair)):
            continue
        reasons[visit] = reason
        for width in BUDGETS:
            block = i // width
            if block > spent[width]:
                spent[width] = block
                selected[width].append(dict(visit=visit, block=block, admitted_index=i, **reason))
    uniforms = {}
    for width, actions in selected.items():
        active = (len(ids) - 1) // width
        count = len(actions)
        midpoints = [1 + ((2 * j + 1) * active) // (2 * count) for j in range(count)]
        uniforms[width] = [
            ids[(block * width + min((block + 1) * width, len(ids)) - 1) // 2]
            for block in midpoints
        ]
    return dict(
        admitted=len(ids),
        eligible=len(reasons),
        policies={f"first_{b}": actions for b, actions in selected.items()}
        | {f"uniform_{b}": [dict(visit=v) for v in values] for b, values in uniforms.items()},
    )


def same_support(wide, capture):
    keys = (
        "session_id",
        "input_manifest_sha256",
        "raw_recording_authority_digest",
        "sample_rate_hz",
        "probe_ms",
        "radio_id",
        "stream_generation",
        "capture_mode",
    )
    top = ("schema_version", "clock_anchor", "delivery_clocks", "last_sample_counter")
    if any(wide[k] != capture[k] for k in top) or any(
        wide["source"][k] != capture["source"][k] for k in keys
    ):
        raise ValueError("native parents do not share their recording and clock authority")
    if wide["provenance"]["excluded_windows"] != capture["provenance"]["excluded_windows"]:
        raise ValueError("the native parents disagree on capture exclusions")
    for (a, wp), (b, cp) in zip(
        visit_pairs(wide["source"]["probes"]), visit_pairs(capture["source"]["probes"]), strict=True
    ):
        if a != b or any(
            {k: v for k, v in x.items() if k != "candidates"}
            != {k: v for k, v in y.items() if k != "candidates"}
            for x, y in zip(wp, cp, strict=True)
        ):
            raise ValueError("a matched physical stereo visit changed support or receiver metadata")


def mix_probes(wide_probes, capture_probes, selected):
    pairs = zip(visit_pairs(wide_probes), visit_pairs(capture_probes), strict=True)
    result, seen = [], set()
    for (visit, wide), (paired, capture) in pairs:
        if visit != paired:
            raise ValueError("paired raw visit order changed")
        if visit in selected:
            result.extend(capture)
            seen.add(visit)
        else:
            result.extend(wide)
    if seen != selected:
        raise ValueError("selection included a missing or invalid visit")
    return result
