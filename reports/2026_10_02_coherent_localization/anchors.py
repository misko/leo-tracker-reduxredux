"""Conservative whole-track anchor selection for coherent localization.

The selector performs no fitting.  It evaluates the supplied parameter point,
assigns at most one frozen catalogue candidate to each admitted track, and
returns original observation rows for the coordinator's joint refiner.
"""

import numpy as np

ALIAS_HZ = 1.0 / 4.4e-6
RESIDUAL_CAP_HZ = 2000.0
MAX_CANDIDATE_SCORE_HZ = 1000.0
MIN_RUNNER_SEPARATION_HZ = 150.0
MIN_GROUPS = 8
MIN_VISIBLE_FRACTION = 0.75
MIN_SUPPORTED_FRACTION = 0.75
MIN_SUPPORTED_DURATION_S = 8.0
MAX_SUPPORT_GAP_S = 4.0
WEIGHT_BLOCK_S = 1.0


def _json_scalar(value):
    if isinstance(value, np.generic):
        return value.item()
    return value


def _circular_residual(measured, prediction):
    return (measured - prediction + ALIAS_HZ / 2) % ALIAS_HZ - ALIAS_HZ / 2


def _supported_duration(times):
    ordered = np.sort(np.asarray(times, dtype=float))
    if len(ordered) < 2:
        return 0.0, None
    gaps = np.diff(ordered)
    return float(np.sum(gaps[gaps <= MAX_SUPPORT_GAP_S])), float(np.max(gaps))


def _block_weights(times):
    blocks = np.floor(np.asarray(times, dtype=float) / WEIGHT_BLOCK_S).astype(np.int64)
    _, inverse, counts = np.unique(blocks, return_inverse=True, return_counts=True)
    weights = 1.0 / counts[inverse]
    return weights, int(len(counts))


def _catalogue_number(data, satellite):
    return _json_scalar(np.asarray(data.numbers)[satellite])


def _candidate_summary(data, candidate):
    return {
        "satellite_index": int(candidate["satellite"]),
        "catalogue_id": _catalogue_number(data, candidate["satellite"]),
        "score_hz": float(candidate["score_hz"]),
        "visible_groups": int(candidate["visible_groups"]),
        "supported_groups": int(candidate["supported_groups"]),
        "supported_duration_s": float(candidate["supported_duration_s"]),
        "residual_median_abs_hz": candidate["residual_median_abs_hz"],
        "residual_p90_abs_hz": candidate["residual_p90_abs_hz"],
    }


def _evaluate_track(data, parameters, track, track_index):
    rows = np.asarray(track["rows"], dtype=np.int64).reshape(-1)
    candidates = np.asarray(track["candidate_indices"], dtype=np.int64).reshape(-1)
    candidates = np.asarray(list(dict.fromkeys(candidates.tolist())), dtype=np.int64)
    track_id = str(track.get("track_id", track_index))
    summary = {
        "track_id": track_id,
        "track_index": int(track_index),
        "accepted": False,
        "rejected_reasons": [],
        "group_count": 0,
        "duration_s": 0.0,
    }
    if not len(rows):
        summary["rejected_reasons"].append("empty_track")
        return None, summary
    if np.any(rows < 0) or np.any(rows >= len(data.times)):
        raise ValueError(f"track {track_id} contains an out-of-range row")
    if not len(candidates):
        summary["rejected_reasons"].append("no_permitted_candidates")
        return None, summary
    if np.any(candidates < 0) or np.any(candidates >= len(data.numbers)):
        raise ValueError(f"track {track_id} contains an out-of-range candidate")

    groups = np.asarray(data.group)[rows]
    unique_groups = np.unique(groups)
    times = np.asarray(data.times, dtype=float)[rows]
    receivers = np.unique(np.asarray(data.receiver)[rows])
    channels = np.unique(np.asarray(data.channel)[rows])
    summary.update(
        group_count=int(len(unique_groups)),
        duration_s=float(np.max(times) - np.min(times)),
        receivers=[_json_scalar(value) for value in receivers],
        channels=[_json_scalar(value) for value in channels],
        candidate_count=int(len(candidates)),
    )
    if len(receivers) != 1:
        summary["rejected_reasons"].append("mixed_receivers")
        return None, summary

    paired_rows = np.tile(rows, len(candidates))
    paired_satellites = np.repeat(candidates, len(rows))
    prediction, visible = data.predict(parameters, rows=paired_rows, satellites=paired_satellites)
    prediction = np.asarray(prediction, dtype=float).reshape(len(candidates), len(rows))
    visible = np.asarray(visible, dtype=bool).reshape(len(candidates), len(rows))
    measured = np.asarray(data.measured, dtype=float)[rows]
    residual = _circular_residual(measured[None, :], prediction)
    valid = (
        visible & np.isfinite(prediction) & np.isfinite(residual) & np.isfinite(measured)[None, :]
    )

    evaluated = []
    for satellite, candidate_residual, candidate_valid in zip(
        candidates, residual, valid, strict=True
    ):
        absolute = np.where(candidate_valid, np.abs(candidate_residual), np.inf)
        order = np.lexsort((rows, absolute, groups))
        first = np.r_[True, groups[order][1:] != groups[order][:-1]]
        representatives = order[first]
        representative_valid = candidate_valid[representatives]
        representative_residual = candidate_residual[representatives]
        capped = np.full(len(unique_groups), RESIDUAL_CAP_HZ)
        capped[representative_valid] = np.minimum(
            np.abs(representative_residual[representative_valid]), RESIDUAL_CAP_HZ
        )
        score_hz = float(np.sqrt(np.mean(capped**2)))
        supported = representative_valid & (np.abs(representative_residual) < RESIDUAL_CAP_HZ)
        support_local = representatives[supported]
        support_rows = rows[support_local]
        support_times = times[support_local]
        supported_duration_s, maximum_gap_s = _supported_duration(support_times)
        visible_residual = np.abs(representative_residual[representative_valid])
        evaluated.append(
            {
                "satellite": int(satellite),
                "score_hz": score_hz,
                "visible_groups": int(np.sum(representative_valid)),
                "supported_groups": int(np.sum(supported)),
                "supported_duration_s": supported_duration_s,
                "maximum_support_gap_s": maximum_gap_s,
                "residual_median_abs_hz": (
                    float(np.median(visible_residual)) if len(visible_residual) else None
                ),
                "residual_p90_abs_hz": (
                    float(np.quantile(visible_residual, 0.9)) if len(visible_residual) else None
                ),
                "residual_rms_hz": (
                    float(np.sqrt(np.mean(representative_residual[supported] ** 2)))
                    if np.any(supported)
                    else None
                ),
                "rows": support_rows,
                "groups": groups[support_local],
                "times": support_times,
            }
        )

    evaluated.sort(key=lambda candidate: (candidate["score_hz"], candidate["satellite"]))
    best = evaluated[0]
    runner = evaluated[1] if len(evaluated) > 1 else None
    separation = runner["score_hz"] - best["score_hz"] if runner is not None else None
    group_count = len(unique_groups)
    visible_fraction = best["visible_groups"] / group_count
    supported_fraction = best["supported_groups"] / group_count
    reasons = summary["rejected_reasons"]
    if group_count < MIN_GROUPS:
        reasons.append("insufficient_groups")
    if visible_fraction < MIN_VISIBLE_FRACTION:
        reasons.append("insufficient_visibility")
    if supported_fraction < MIN_SUPPORTED_FRACTION:
        reasons.append("insufficient_supported_fraction")
    if best["supported_duration_s"] < MIN_SUPPORTED_DURATION_S:
        reasons.append("insufficient_supported_duration")
    if best["score_hz"] > MAX_CANDIDATE_SCORE_HZ:
        reasons.append("inconsistent_residual")
    if separation is not None and separation < MIN_RUNNER_SEPARATION_HZ:
        reasons.append("runner_up_too_close")

    summary.update(
        receiver=_json_scalar(receivers[0]),
        satellite_index=int(best["satellite"]),
        catalogue_id=_catalogue_number(data, best["satellite"]),
        score_hz=float(best["score_hz"]),
        visible_groups=int(best["visible_groups"]),
        visible_fraction=float(visible_fraction),
        supported_groups=int(best["supported_groups"]),
        supported_fraction=float(supported_fraction),
        supported_duration_s=float(best["supported_duration_s"]),
        maximum_support_gap_s=best["maximum_support_gap_s"],
        residual_median_abs_hz=best["residual_median_abs_hz"],
        residual_p90_abs_hz=best["residual_p90_abs_hz"],
        residual_rms_hz=best["residual_rms_hz"],
        runner_up=(
            {
                **_candidate_summary(data, runner),
                "separation_hz": float(separation),
            }
            if runner is not None
            else None
        ),
        leading_candidates=[_candidate_summary(data, candidate) for candidate in evaluated[:3]],
    )
    proposal = {
        "summary": summary,
        "rows": best["rows"],
        "groups": best["groups"],
        "times": best["times"],
        "all_groups": unique_groups,
        "satellite": best["satellite"],
        "receiver": _json_scalar(receivers[0]),
        "rank_key": (
            -best["supported_duration_s"],
            best["score_hz"],
            -(separation if separation is not None else RESIDUAL_CAP_HZ),
            -best["supported_groups"],
            track_index,
        ),
    }
    return proposal, summary


def _select_with_receiver_coverage(proposals, max_tracks):
    ranked = sorted(proposals, key=lambda proposal: proposal["rank_key"])
    receiver_order = []
    for proposal in ranked:
        if proposal["receiver"] not in receiver_order:
            receiver_order.append(proposal["receiver"])
    chosen = []
    chosen_ids = set()
    used_groups = set()

    def admit(proposal):
        groups = set(proposal["all_groups"].tolist())
        if groups & used_groups:
            return False
        chosen.append(proposal)
        chosen_ids.add(id(proposal))
        used_groups.update(groups)
        return True

    for receiver in receiver_order[:max_tracks]:
        for proposal in ranked:
            if (
                proposal["receiver"] == receiver
                and id(proposal) not in chosen_ids
                and admit(proposal)
            ):
                break
    for proposal in ranked:
        if len(chosen) >= max_tracks:
            break
        if id(proposal) not in chosen_ids:
            admit(proposal)
    chosen.sort(key=lambda proposal: proposal["rank_key"])
    return ranked, chosen


def select_anchors(data, parameters, max_tracks=12):
    """Select reliable fixed-identity track anchors without changing observations.

    Duplicate alternatives in a source group are represented by the visible row
    with the smallest absolute circular residual, with the original row index as
    the deterministic tie-break.  Only residual-supported representatives are
    returned.  Within each admitted track, every occupied absolute one-second
    time block has total weight one, divided equally among rows in that block.
    Thus a track's total weight is exactly its number of occupied blocks.
    """

    if isinstance(max_tracks, bool) or int(max_tracks) != max_tracks or max_tracks < 0:
        raise ValueError("max_tracks must be a non-negative integer")
    max_tracks = int(max_tracks)
    lengths = {
        len(np.asarray(getattr(data, name)))
        for name in ("times", "measured", "rf", "receiver", "channel", "group")
    }
    if len(lengths) != 1:
        raise ValueError("data observation arrays must have equal lengths")

    proposals = []
    summaries = []
    for track_index, track in enumerate(data.tracks):
        proposal, summary = _evaluate_track(data, parameters, track, track_index)
        summaries.append(summary)
        if proposal is not None and not summary["rejected_reasons"]:
            proposals.append(proposal)

    ranked, chosen = _select_with_receiver_coverage(proposals, max_tracks)
    chosen_ids = {id(proposal) for proposal in chosen}
    used_groups = set()
    for proposal in chosen:
        used_groups.update(proposal["all_groups"].tolist())
    for rank, proposal in enumerate(ranked, start=1):
        summary = proposal["summary"]
        summary["quality_rank"] = rank
        if id(proposal) in chosen_ids:
            summary["accepted"] = True
        else:
            overlap = set(proposal["all_groups"].tolist()) & used_groups
            summary["rejected_reasons"].append(
                "group_conflict" if overlap else "max_tracks_reached"
            )
            summary["conflicting_group_count"] = int(len(overlap))

    output_rows = []
    output_satellites = []
    output_weights = []
    selected_summaries = []
    for proposal in chosen:
        order = np.lexsort((proposal["rows"], proposal["times"]))
        rows = proposal["rows"][order]
        times = proposal["times"][order]
        weights, effective_groups = _block_weights(times)
        output_rows.append(rows)
        output_satellites.append(np.full(len(rows), proposal["satellite"], dtype=np.int64))
        output_weights.append(weights)
        summary = proposal["summary"]
        summary["selected_rows"] = int(len(rows))
        summary["effective_groups"] = effective_groups
        summary["weight_sum"] = float(np.sum(weights))
        selected_summaries.append(summary)

    rows = np.concatenate(output_rows) if output_rows else np.empty(0, dtype=np.int64)
    satellites = (
        np.concatenate(output_satellites) if output_satellites else np.empty(0, dtype=np.int64)
    )
    weights = np.concatenate(output_weights) if output_weights else np.empty(0, dtype=float)
    if len(rows) and len(np.unique(np.asarray(data.group)[rows])) != len(rows):
        raise AssertionError("anchor source groups are not exclusive")

    diagnostics = {
        "policy": {
            "alias_period_hz": ALIAS_HZ,
            "residual_cap_hz": RESIDUAL_CAP_HZ,
            "candidate_score": (
                "RMS of absolute circular residual capped at 2000 Hz, with invisible or "
                "non-finite source groups charged the 2000 Hz cap"
            ),
            "maximum_candidate_score_hz": MAX_CANDIDATE_SCORE_HZ,
            "minimum_runner_up_separation_hz": MIN_RUNNER_SEPARATION_HZ,
            "minimum_groups": MIN_GROUPS,
            "minimum_visible_fraction": MIN_VISIBLE_FRACTION,
            "minimum_supported_fraction": MIN_SUPPORTED_FRACTION,
            "minimum_supported_duration_s": MIN_SUPPORTED_DURATION_S,
            "maximum_counted_support_gap_s": MAX_SUPPORT_GAP_S,
            "supported_duration": (
                "sum of adjacent supported time differences no larger than 4 seconds"
            ),
            "ranking": (
                "supported duration descending, candidate score ascending, runner-up "
                "separation descending, supported groups descending, source order"
            ),
            "receiver_coverage": (
                "reserve one quality-gated, group-compatible track per represented receiver "
                "when max_tracks permits; never bypass a quality gate"
            ),
            "group_exclusivity": (
                "admitted whole tracks may not share any source group, including groups not "
                "returned as residual-supported anchors"
            ),
            "weighting": (
                "within each track and floor(time_s / 1 s) block, rows split unit weight; "
                "track weight therefore equals its occupied one-second blocks"
            ),
        },
        "evaluated_track_count": len(summaries),
        "quality_gated_track_count": len(proposals),
        "selected_track_count": len(chosen),
        "selected_row_count": int(len(rows)),
        "selected_receivers": sorted(
            {_json_scalar(proposal["receiver"]) for proposal in chosen}, key=str
        ),
        "evaluated_tracks": summaries,
        "rejected": [summary for summary in summaries if not summary["accepted"]],
    }
    return {
        "rows": rows,
        "satellites": satellites,
        "weights": weights,
        "tracks": selected_summaries,
        "diagnostics": diagnostics,
    }
