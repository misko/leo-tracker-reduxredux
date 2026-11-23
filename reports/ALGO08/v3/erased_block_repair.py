"""Forecast held signed Doppler after erasing it from the forward receiver history."""

from collections import Counter, defaultdict
from time import process_time, perf_counter

import numpy as np

from crossfit_future_coverage import BLOCK_S, erase, identifier
from local_future_inputs import MAX_GAP_S, selection


ARMS = ("c0", "fitted_c")
MIN_HELD_VISITS = 2


def clock(start):
    cpu, wall = start
    return dict(cpu_s=process_time()-cpu, elapsed_s=perf_counter()-wall)


def now():
    return process_time(), perf_counter()


def central_block(blocks):
    occupied = sorted((row for row in blocks if row["held"]), key=lambda row: row["block"])
    if not occupied:
        raise ValueError("No occupied future-only blocks")
    return occupied[(len(occupied)-1)//2]


def guarded_selection(native, block):
    held_ids = set(block["held_ids"])
    source = native["source"]
    receivers = sorted({p["receiver_id"] for p in source["probes"]})
    rows = []
    for row in source["probes"]:
        oid = identifier(source["session_id"], row)
        if oid in held_ids:
            # Same time convention as winning_observations. Do not read candidates here.
            time = (row["valid_start_counter"]-native["clock_anchor"]["sample_counter"])/source["sample_rate_hz"]
            time += source["probe_ms"]*.0005
            if int(time//BLOCK_S) != block["block"]:
                raise ValueError("An enrolled held slot falls outside its recorded block")
            rows.append(dict(observation_id=oid, time_s=time, receiver=receivers.index(row["receiver_id"])+1,
                             actual_rf_hz=float(row["actual_rf_hz"]), channel=int(row["channel"]), visit=row["visit_index"]))
    forward, regenerated = selection(erase(native, held_ids))
    training = [row for row in regenerated if abs(int(row["time_s"]//BLOCK_S)-block["block"]) > 1]
    if (len(rows) != len(held_ids)
            or any(identifier(source["session_id"], row) in held_ids and row["candidates"] for row in forward["source"]["probes"])
            or any(row["observation_id"] in held_ids for row in training)):
        raise ValueError("Held receiver evidence re-entered the training selection")
    return forward, training, rows, len(regenerated)


def anchor_lift(track, keep, known, target, period):
    choices = [(abs(time-target), time, oid, value) for time, oid, value in
               zip(track["times"], track["observation_ids"], track["values"], strict=True)
               if oid in keep and abs(time-target) <= MAX_GAP_S]
    if not choices:
        return None
    _, _, oid, fitted_value = min(choices)
    anchor = known[oid]
    delta = fitted_value - anchor["measured_cfo_hz"]
    lift = int(round(delta/period))
    if not np.isclose(delta, lift*period, atol=1e-6, rtol=0.):
        return None
    return lift, oid, anchor["fractional_margin"]


def held_targets(prepared, signed, held):
    from local_future_repair import PERIOD, memberships, nominate

    original = memberships(signed, "c0")
    if original != memberships(signed, "fitted_c"):
        raise ValueError("Forward arms disagree on original memberships")
    proposals = defaultdict(list)
    for index, role, row in nominate(signed["scan"].tracks, original, held):
        proposals[row["observation_id"]].append((index, role))
    known = {row["observation_id"]: row for row in prepared["tracks"]["observations"]}
    points, reasons = [], Counter()
    for row in held:
        options = proposals[row["observation_id"]]
        if len(options) != 1:
            reasons["ambiguous_track" if options else "no_existing_same_lane_track"] += 1
            continue
        (index, role), = options
        track = signed["scan"].tracks[index]
        _, norad, keep = original[track["key"]]
        anchor = anchor_lift(track, keep, known, row["time_s"], PERIOD)
        if anchor is None:
            reasons["unresolved_original_graph_lift"] += 1
            continue
        lift, oid, margin = anchor
        points.append(dict(row, role=role, track_index=index, component=track["key"], norad=norad,
                           lift=lift, anchor_id=oid, anchor_margin=margin))
    return original, points, dict(reasons)


def predicted(signed, points):
    from local_future_repair import enlarged, fixed_context, predict

    grouped = defaultdict(list)
    for row in points:
        # This placeholder is never fitted or scored. Only fixed posterior means are evaluated.
        placeholder = dict(row, fractional_margin=row["anchor_margin"], measured_cfo_hz=0.)
        grouped[row["track_index"]].append((placeholder, row["lift"]))
    states = {arm: fixed_context(signed, arm) for arm in ARMS}
    shadow = enlarged(signed, states["c0"][2], grouped)
    offsets = {i: {oid: j for j, oid in enumerate(shadow["scan"].tracks[i]["observation_ids"])} for i in grouped}
    predictions = {row["observation_id"]: {} for row in points}
    for arm in ARMS:
        _, _, conditional, predictive, biases = predict(shadow, arm, states[arm])
        for row in points:
            oid, i, role = (row[key] for key in ("observation_id", "track_index", "role"))
            residual, elevation = (conditional if role == "conditional" else predictive)[i]
            j = offsets[i][oid]
            prediction = (0. if role == "conditional" else biases[i]) - residual[j]
            predictions[oid][arm] = dict(signed_cfo_hz=float(prediction), elevation_deg=float(elevation[j]))
    return predictions


def finite_visible(arm):
    return np.isfinite(arm["signed_cfo_hz"]) and np.isfinite(arm["elevation_deg"]) and arm["elevation_deg"] >= 0


def compare(prepared, signed, training, held):
    from local_future_repair import attach, nominate

    timer = now()
    original, targets, reasons = held_targets(prepared, signed, held)
    proposed_training = list(nominate(signed["scan"].tracks, original, training))
    result = dict(forward_tracks=len(original), forward_owners=sum(len(row[2]) for row in original.values()),
                  training_compatible_lane_hypotheses=len(proposed_training), held_unique_labeled=len(targets),
                  excluded_held_by_reason=reasons, admission_clock=clock(timer))
    timer = now()
    forward = predicted(signed, targets) if targets else {}
    keep = [row for row in targets if all(finite_visible(value) for value in forward[row["observation_id"]].values())]
    visits = len({row["visit"] for row in keep})
    result.update(held_visible=len(keep), held_visits=visits,
                  held_groups=len({(row["norad"], row["receiver"]) for row in keep}),
                  forward_prediction_clock=clock(timer))
    rows = [dict(row, forward=forward[row["observation_id"]]) for row in keep]
    result["held_predictions"] = rows
    if visits < MIN_HELD_VISITS or not proposed_training:
        result["status"] = "insufficient_independent_held_visits" if visits < MIN_HELD_VISITS else "no_training_attachment_hypotheses"
        return result
    measured = {}
    _, fitted = attach(prepared, signed, measured, training)
    result["training_fit"] = {key: value for key, value in measured["local_future_repair"].items() if key != "refitted"}
    if fitted is signed:
        result["status"] = "no_qualified_training_update"
        return result
    timer = now()
    updated = predicted(fitted, keep)
    for row in rows:
        row["updated"] = updated[row["observation_id"]]
    result.update(status="paired_predictions_sealed", updated_prediction_clock=clock(timer))
    return result


def paired_rf_scores(rows, measured):
    result = {}
    for arm in ARMS:
        variants = ("forward", "updated")
        residuals = {name: np.asarray([measured[row["observation_id"]]-row[name][arm]["signed_cfo_hz"] for row in rows])
                     for name in variants}
        if any(not np.isfinite(array).all() for array in residuals.values()):
            raise ValueError("Held predictions yielded nonfinite signed errors")
        scores = {name: dict(rms_hz=float(np.sqrt(np.mean(r*r))), signed_mean_hz=float(r.mean()),
                             squared_hz2=float(r @ r), signed_residual_hz=r.tolist()) for name, r in residuals.items()}
        scores["updated_minus_forward_squared_hz2"] = scores["updated"]["squared_hz2"]-scores["forward"]["squared_hz2"]
        scores["updated_below_horizon"] = sum(row["updated"][arm]["elevation_deg"] < 0 for row in rows)
        result[arm] = scores
    return result
