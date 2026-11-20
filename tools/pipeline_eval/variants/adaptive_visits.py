"""Select bounded original-detector visits from causal fast pilot tracks."""

import json
from collections import Counter, defaultdict
from hashlib import sha256

from .negative_rescue import GATE, positive
from .selective_capture import ALIAS, same_support, visit_pairs, wrapped

SALT = "adaptive-visits/v1"
STRIDE = 16
FRAME_HZ = 750
CAPTURE_S = 300
MAX_AGE_S = 12
MARGIN = "fractional_margin"
RANK = "candidate_rank"
CFO = "fractional_tracking_cfo_hz"


def digest(*parts):
    return sha256(
        json.dumps([SALT, *parts], sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def winner(probe):
    return max(
        (c for c in probe["candidates"] if c[GATE]),
        key=lambda c: (c[MARGIN], -c[RANK]),
        default=None,
    )


def residual(track, point, frame):
    previous, last = track
    now, frequency, phase = point
    then, f, e = last
    gap = now - then
    if previous is not None:
        elapsed = then - previous[0]
        if elapsed > 0:
            f += min(30_000, max(-30_000, wrapped(f - previous[1], ALIAS) / elapsed)) * gap
            e += min(30, max(-30, wrapped(e - previous[2], frame) / elapsed)) * gap
    return max(
        abs(wrapped(frequency - f, ALIAS)) / (6_000 + 4_000 * gap),
        abs(wrapped(phase - e, frame)) / (24 + 10 * gap),
    )


def novelty(tracks, point, sec, frame):
    tracks[:] = [track for track in tracks if sec - track[1][0] <= MAX_AGE_S]
    if point is None:
        return 2.0 if any(a is not None and sec - b[0] <= 3 for a, b in tracks) else 0.0
    if tracks:
        score, index = min((residual(track, point, frame), i) for i, track in enumerate(tracks))
        if score <= 1:
            tracks[index] = tracks[index][1], point
            return score
    else:
        score = 0.0
    tracks.append((None, point))
    tracks.sort(key=lambda track: track[1][0], reverse=True)
    del tracks[4:]
    return min(4.0, score)


def visit_scores(fast):
    tracks = defaultdict(list)
    source = fast["source"]
    rate = source["sample_rate_hz"]
    frame = rate / FRAME_HZ
    t0 = fast["clock_anchor"]["sample_counter"]
    clocks = fast["delivery_clocks"]
    arrival_zero = clocks[0]["monotonic_ns"]
    for visit, pair in visit_pairs(source["probes"]):
        clock = clocks[visit]["monotonic_ns"]
        if clock - arrival_zero > CAPTURE_S * 1_000_000_000:
            return
        rf = int(pair[0]["actual_rf_hz"])
        if rf <= 0 or any(probe["actual_rf_hz"] != rf for probe in pair):
            raise ValueError("expected an identical RF center on both antennas")
        scores = []
        for rx, probe in enumerate(pair):
            samples = probe["valid_start_counter"] - t0
            sec = samples / rate
            candidate = winner(probe)
            point = (
                None
                if candidate is None
                else (
                    sec,
                    candidate[CFO],
                    (
                        samples
                        + candidate["integer_epoch_sample"]
                        + candidate["fractional_epoch_offset_samples"]
                    )
                    % frame,
                )
            )
            scores.append(novelty(tracks[rf, rx], point, sec, frame))
        yield dict(visit=visit, rf_hz=rf, score=max(scores), arrival_ns=clock - arrival_zero)


def schedule(rows, threshold):
    """Spend at most one token for each 16 elapsed RF visits."""
    counts, spent = Counter(), set()
    windows, selected = defaultdict(list), []
    for item in rows:
        rf = item["rf_hz"]
        counts[rf] += 1
        window, offset = divmod(counts[rf], STRIDE)
        if not window:
            continue
        key = rf, window
        record = dict(item, token=window)
        windows[key].append(record)
        if key not in spent and (record["score"] >= threshold or offset == STRIDE - 1):
            selected.append(
                dict(record, trigger="novelty" if record["score"] >= threshold else "expiry")
            )
            spent.add(key)
    return selected, windows


def matched_control(manifest, selected, windows):
    rows = []
    for item in selected:
        rf, window = item["rf_hz"], item["token"]
        control = min(
            windows[rf, window],
            key=lambda row: digest("control", manifest, rf, window, row["visit"]),
        )
        rows.append(dict(control, trigger="hash"))
    return sorted(rows, key=lambda row: row["visit"])


def project(fast, original, selected):
    """Transfer authentic complete stereo packets and preserve the per-probe lineage."""
    same_support(fast, original)
    wanted = {row["visit"]: row for row in selected}
    if len(wanted) != len(selected):
        raise ValueError("an original visit can only be requested once")
    rows, lineage = [], []
    pairs = zip(
        visit_pairs(fast["source"]["probes"]),
        visit_pairs(original["source"]["probes"]),
        strict=True,
    )
    for (visit, quick), (other, deep) in pairs:
        if visit != other:
            raise ValueError("position inputs disagree about the physical visit")
        if visit not in wanted:
            rows.extend(quick)
            continue
        action = wanted.pop(visit)
        rows.extend(deep)
        for rx, (a, b) in enumerate(zip(quick, deep, strict=True)):
            lineage.append(
                dict(
                    action,
                    rx=rx,
                    fast_positive=positive(a),
                    original_positive=positive(b),
                    changed=a["candidates"] != b["candidates"],
                    winner_changed=winner(a) != winner(b),
                    fast_candidate_sha256=digest(
                        "candidates", sorted(a["candidates"], key=lambda c: c[RANK])
                    ),
                    original_candidate_sha256=digest(
                        "candidates", sorted(b["candidates"], key=lambda c: c[RANK])
                    ),
                )
            )
    if wanted:
        raise ValueError("visit selection is outside the authenticated native support")
    return rows, lineage
