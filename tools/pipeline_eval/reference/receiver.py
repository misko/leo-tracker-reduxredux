"""Select and verify a local receiver fix from anonymous Doppler tracks."""

import math
from itertools import pairwise
from time import perf_counter

from . import grid

MAX_TRACKS = 64
MIN_TRACKS = 4
MIN_SHAPE_SCORE = 0.25
MIN_REGION_LEAD = 0.025
MIN_NULL_LEAD = 0.02
NULL_COUNT = 19
MIN_RETIME_SLACK_S = 1e-6
MAX_SPLIT_SEPARATION_KM = 5.0
MAX_POOLED_DISPLACEMENT_KM = 4.0
MIN_BOUNDARY_CLEARANCE_KM = 1.0
TIE_TOLERANCE = 1e-12


def _offered_regions(regions):
    offered = {}
    for region in regions:
        region_id = region["id"]
        lat, lon = map(float, region["center"])
        if not isinstance(region_id, str) or not -90 <= lat <= 90 or not math.isfinite(lon):
            raise ValueError("invalid region ID or center")
        center = (lat, (lon + 180.0) % 360.0 - 180.0)
        if region_id in offered and offered[region_id] != center:
            raise ValueError("same region ID identifies different centers")
        offered[region_id] = center
    return sorted(offered.items(), key=lambda item: (item[1], item[0]))


def _track_key(track):
    times = track["times"]
    return (
        times[0] - times[-1],
        times,
        track["rf_hz"],
        type(track["receiver"]).__name__,
        track["receiver"],
        type(track["channel"]).__name__,
        track["channel"],
        track["values"],
    )


def _screen_tracks(records, duration):
    tracks = {}
    for record in records:
        try:
            samples = sorted(
                zip(map(float, record["times"]), map(float, record["values"]), strict=True)
            )
            times, values = zip(*samples, strict=True)
            rf_hz = float(record["rf_hz"])
            receiver, channel = record["receiver"], record["channel"]
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if (
            len(times) < 4
            or any(not math.isfinite(value) for sample in samples for value in sample)
            or not 0 <= times[0] < times[-1] <= duration
            or any(b <= a for a, b in pairwise(times))
            or not math.isfinite(rf_hz)
            or rf_hz <= 0
            or not isinstance(receiver, (str, int))
            or not isinstance(channel, (str, int))
        ):
            continue
        track = dict(times=times, values=values, rf_hz=rf_hz, receiver=receiver, channel=channel)
        tracks[_track_key(track)] = track
    return [tracks[key] for key in sorted(tracks)]


def _shifted(tracks, midpoint, duration, step):
    shifted = []
    for track in tracks:
        times = track["times"]
        slack = (duration - midpoint) - (times[-1] - times[0])
        if slack <= MIN_RETIME_SLACK_S:
            shifted.append(track)
            continue
        start = midpoint + (times[0] - midpoint + slack * step / (NULL_COUNT + 1)) % slack
        shifted.append(dict(track, times=tuple(start + (t - times[0]) for t in times)))
    return shifted


def _metrics(record):
    if record is None:
        return None
    return {key: record[key] for key in ("score", "n_tracks", "rms_hz")}


def _enough_signal(metrics):
    return (
        metrics is not None
        and metrics["score"] is not None
        and metrics["score"] >= MIN_SHAPE_SCORE
        and metrics["n_tracks"] >= MIN_TRACKS
    )


def _score_value(metrics):
    return 0.0 if metrics is None or metrics["score"] is None else metrics["score"]


def _leaders(ranked, metric):
    """Rank on evidence, using physical coordinates for forced exact-score ties."""
    ranked = sorted(ranked, key=lambda row: (-_score_value(row[metric]), row["center"]))
    if not ranked:
        return None, None, []
    first = ranked[0]
    top_score = _score_value(first[metric])
    tied = [row for row in ranked if top_score - _score_value(row[metric]) <= TIE_TOLERANCE]
    winner = min(tied, key=lambda row: row["center"])
    runner = _score_value(ranked[1][metric]) if len(ranked) > 1 else None
    peers = sorted(row["id"] for row in tied)
    if sum(row["center"] == winner["center"] for row in tied) > 1:
        winner = dict(winner, id=None)
    return winner, runner, peers


def _region_reason(early, held, region_lead, null_lead):
    if not _enough_signal(early) or not _enough_signal(held):
        return "weak_regional_signal"
    if region_lead is not None and region_lead <= MIN_REGION_LEAD:
        return "ambiguous_region"
    if null_lead is None:
        return "insufficient_changed_time_controls"
    if null_lead <= MIN_NULL_LEAD:
        return "failed_changed_time_controls"
    return "accepted"


def _position_check(early, late, pooled):
    if not _enough_signal(late) or not _enough_signal(pooled):
        return "weak_position_signal", {}
    split = math.dist(early["xy"], late["xy"])
    from_early = math.dist(pooled["xy"], early["xy"])
    from_late = math.dist(pooled["xy"], late["xy"])
    clearance = grid.HALF_WIDTH_KM - max(map(abs, pooled["xy"]))
    distances = dict(
        early_late_km=split,
        pooled_early_km=from_early,
        pooled_late_km=from_late,
        pooled_boundary_clearance_km=clearance,
    )
    if split > MAX_SPLIT_SEPARATION_KM or max(from_early, from_late) > MAX_POOLED_DISPLACEMENT_KM:
        return "inconsistent_position", distances
    if clearance <= MIN_BOUNDARY_CLEARANCE_KM:
        return "position_at_tile_boundary", distances
    return "accepted", distances


def solve(observation, regions, tle_text):
    """Return a validated scan-end fix or a withheld result with forced diagnostics."""
    started = perf_counter()
    stages = {}
    work = dict(tiles=0, grid_fits=0, point_scores=0, null_schedules=0)
    diagnostics = dict(stage_seconds=stages, work=work)

    def finish(reason, winner=None, best=None):
        diagnostics.setdefault(
            "region_result", dict(status="withheld", region_id=None, reason=reason)
        )
        diagnostics["wall_s"] = perf_counter() - started
        published = reason == "accepted"
        best_region = None if winner is None else winner["id"]
        best_latlon = None if best is None else [float(x) for x in best["latlon"]]
        return dict(
            status="fix" if published else "withheld",
            region_id=best_region if published else None,
            latlon=best_latlon if published else None,
            reason=reason,
            best_region=best_region,
            best_latlon=best_latlon,
            diagnostics=diagnostics,
        )

    def fit(tile, tracks):
        work["grid_fits"] += 1
        return grid.fit_grid(tile, tracks)

    def score(nominee, tracks):
        work["point_scores"] += 1
        return grid.score_at(nominee["tile"], tracks, nominee["early"]["xy"])

    try:
        duration = float(observation["duration_s"])
        if not math.isfinite(duration) or duration <= 0:
            return finish("invalid_duration")
        offered = _offered_regions(regions)
        records = observation["tracks"]
        if not isinstance(records, (list, tuple)):
            raise TypeError("tracks must be a sequence of track records")
    except (KeyError, TypeError, ValueError, OverflowError):
        return finish("invalid_observation_or_region_list")
    if not offered:
        return finish("no_regions")

    tracks = _screen_tracks(records, duration)
    midpoint = duration / 2
    early = [t for t in tracks if t["times"][-1] <= midpoint][:MAX_TRACKS]
    late = [t for t in tracks if t["times"][0] >= midpoint][:MAX_TRACKS]
    pooled_tracks = tracks[:MAX_TRACKS]
    diagnostics["track_counts"] = dict(
        received=len(records),
        screened=len(tracks),
        early=len(early),
        late=len(late),
        pooled=len(pooled_tracks),
    )
    stages["input"] = perf_counter() - started
    if len(pooled_tracks) < MIN_TRACKS:
        return finish("insufficient_tracks")

    mark = perf_counter()
    try:
        sky = grid.prepare_sky(observation, tle_text)
    except (KeyError, TypeError, ValueError, OverflowError):
        stages["sky"] = perf_counter() - mark
        return finish("invalid_causal_catalogue")
    stages["sky"] = perf_counter() - mark
    diagnostics["sky"] = sky.stats
    mark = perf_counter()
    rows = [
        dict(id=region_id, center=center, tile=grid.make_tile(sky, center))
        for region_id, center in offered
    ]
    work["tiles"] = len(rows)
    diagnostics["tile_work"] = {row["id"]: row["tile"].stats for row in rows}
    stages["tiles"] = perf_counter() - mark

    mark = perf_counter()
    for row in rows:
        row["early"] = fit(row["tile"], early) if len(early) >= MIN_TRACKS else None
    nominees = [row for row in rows if row["early"] is not None]
    stages["early_nomination"] = perf_counter() - mark

    mark = perf_counter()
    for row in nominees:
        row["held"] = score(row, late) if len(late) >= MIN_TRACKS else None
    ranked = [row for row in nominees if _score_value(row["held"]) > 0]
    diagnostics["regional_scores"] = {
        row["id"]: dict(early=_metrics(row["early"]), held=_metrics(row.get("held")))
        for row in rows
    }
    stages["held_scoring"] = perf_counter() - mark

    mark = perf_counter()
    winner, runner, ties = _leaders(ranked, "held")
    if winner is None:
        for row in rows:
            row["pooled"] = fit(row["tile"], pooled_tracks)
        stages["pooled_fit"] = perf_counter() - mark
        winner, _, ties = _leaders([row for row in rows if row["pooled"] is not None], "pooled")
        diagnostics["forced_source"] = "pooled_only" if winner is not None else None
        diagnostics["tied_region_ids"] = ties if len(ties) > 1 else []
        reason = (
            "insufficient_disjoint_tracks"
            if min(len(early), len(late)) < MIN_TRACKS
            else "no_held_nominee"
        )
        return finish(reason, winner, None if winner is None else winner["pooled"])

    pooled = fit(winner["tile"], pooled_tracks)
    best = pooled if pooled is not None else winner["early"]
    stages["pooled_fit"] = perf_counter() - mark
    diagnostics["forced_source"] = "pooled" if pooled is not None else "early"
    diagnostics["tied_region_ids"] = ties if len(ties) > 1 else []

    mark = perf_counter()
    observed_score = _score_value(winner["held"])
    region_lead = None if runner is None else observed_score - runner
    movable = sum(
        (duration - midpoint) - (t["times"][-1] - t["times"][0]) > MIN_RETIME_SLACK_S for t in late
    )
    null_maxima = []
    if movable >= MIN_TRACKS:
        for step in range(1, NULL_COUNT + 1):
            changed = _shifted(late, midpoint, duration, step)
            null_maxima.append(max(_score_value(score(row, changed)) for row in nominees))
        work["null_schedules"] = len(null_maxima)
    null_lead = observed_score - max(null_maxima) if null_maxima else None
    diagnostics["held_evidence"] = dict(
        score=observed_score,
        region_lead=region_lead,
        null_lead=null_lead,
        movable_tracks=movable,
        null_maxima=null_maxima,
        null_exceedances=sum(s >= observed_score for s in null_maxima) if null_maxima else None,
    )
    stages["time_shift_controls"] = perf_counter() - mark

    reason = _region_reason(winner["early"], winner["held"], region_lead, null_lead)
    if reason != "accepted":
        return finish(reason, winner, best)
    diagnostics["region_result"] = dict(
        status="accepted", region_id=winner["id"], reason="accepted"
    )

    mark = perf_counter()
    late_fit = fit(winner["tile"], late)
    reason, distances = _position_check(winner["early"], late_fit, pooled)
    diagnostics["position_evidence"] = dict(
        early=_metrics(winner["early"]),
        late=_metrics(late_fit),
        pooled=_metrics(pooled),
        **distances,
    )
    stages["position_check"] = perf_counter() - mark
    return finish(reason, winner, best)
