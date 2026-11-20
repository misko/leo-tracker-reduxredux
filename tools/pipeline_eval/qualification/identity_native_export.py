"""Trace the frozen anonymous receiver without changing its selected input factors."""

from hashlib import sha256
from unittest.mock import patch

import numpy as np

from ..variants import independent_arcs as independent
from ..variants import peak_paths as stock


def export(capture, offer):
    state = {}
    decoder = stock.decode
    original_bank = stock.orbital_bank
    slice_orbit = stock.slice_orbit
    geometry = stock.orbit_geometry
    shortlist = independent.shortlist
    unique = independent.unique
    original_check = independent.checked_time
    training_columns = {}

    def capture_bank(*a, **kw):
        bank, norads, sky = original_bank(*a, **kw)
        state["norads"] = norads
        return bank, norads, sky

    def capture_shortlist(bank, lane, pairs, lane_no):
        batches = {}
        selected = {}

        def capture_slice(bank, indices):
            selected["indices"] = indices
            return slice_orbit(bank, indices)

        def capture_geometry(bank, times, phase, *a, **kw):
            selected["phase"] = phase
            return geometry(bank, times, phase, *a, **kw)

        def record(lane, pred, *, fixed=False):
            score, columns = decoder(lane, pred, fixed=fixed)
            for number, k in zip(selected["indices"], columns, strict=True):
                batches[int(number), selected["phase"]] = k
            return score, columns

        with (
            patch.object(stock, "slice_orbit", capture_slice),
            patch.object(stock, "orbit_geometry", capture_geometry),
            patch.object(stock, "decode", record),
        ):
            found, searched = shortlist(bank, lane, pairs, lane_no)
        for a in found:
            k = batches[a["orbit"], a["phase"]]
            use = np.flatnonzero(k >= 0)
            training_columns[lane_no, a["orbit"], a["phase"]] = dict(
                zip(lane.visit[use], k[use], strict=True)
            )
        return found, searched

    def training_unique(arcs, lanes):
        rows = unique(arcs, lanes)
        if "train" in state:
            return rows
        trace = [
            a
            | {
                "columns": [
                    training_columns[a["lane"], a["orbit"], a["phase"]][v] for v in a["visit"]
                ]
            }
            for a in rows
        ]
        state["train"] = flatten(trace, lanes, state["norads"])
        return rows

    def capture_held(bank, lanes, pair_ids, arcs, level, solution):
        if "held" in state:
            return original_check(bank, lanes, pair_ids, arcs, level, solution)
        decoded = {}
        iterator = iter(arcs)

        def record(lane, pred, *, fixed=False):
            horizontal, picks = decoder(lane, pred, fixed=fixed)
            a = next(iterator)
            key = (a["lane"], a["orbit"])
            if key in decoded:
                raise ValueError("two held decodes have the same lane and causal orbit")
            use = np.flatnonzero(picks[0] >= 0)
            decoded[key] = dict(
                zip(
                    lane.visit[use],
                    zip(lane.y[use, picks[0, use]], picks[0, use], strict=True),
                    strict=True,
                )
            )
            return horizontal, picks

        def held_unique(options, attempted):
            held = unique(options, attempted)
            physical = []
            for a in held:
                index = decoded[a["lane"], a["orbit"]]
                y, cols = zip(*(index[v] for v in a["visit"]), strict=True)
                physical.append(a | {"y": y, "columns": cols})
            state["held"] = flatten(physical, lanes, state["norads"])
            return held

        with (
            patch.object(stock, "decode", record),
            patch.object(independent, "unique", held_unique),
        ):
            return original_check(bank, lanes, pair_ids, arcs, level, solution)

    with (
        patch.object(stock, "orbital_bank", capture_bank),
        patch.object(independent, "shortlist", capture_shortlist),
        patch.object(independent, "unique", training_unique),
        patch.object(independent, "checked_time", capture_held),
    ):
        result = independent.solve(capture, tile=offer)
    train, held = state.get("train", []), state.get("held", [])
    if len(train) != result["metrics"]["selected_points"] or len(held) != result["arms"]["c0"].get(
        "held_points", 0
    ):
        raise ValueError("traced native points differ from the frozen anonymous receiver")
    return result, train, held


def flatten(arcs, lanes, norads):
    return [
        dict(
            receiver=lanes[a["lane"]].key[0],
            channel=lanes[a["lane"]].key[1],
            rf_hz=lanes[a["lane"]].key[2],
            orbit=norads[a["orbit"]],
            visit=int(v),
            time_s=float(t),
            wrapped_hz=float(y),
            candidate_column=int(k),
        )
        for a in arcs
        for v, t, y, k in zip(a["visit"], a["t"], a["y"], a["columns"], strict=True)
    ]


def physical_index(capture, source):
    native, original = {}, {}
    for probe in capture.probes:
        rx, visit = probe["receiver_id"], probe["visit_index"]
        counter = probe["valid_start_counter"]
        key = rx, visit
        identifier = "sha256:" + sha256(f"{source}:{rx}:{counter}".encode()).hexdigest()
        if key in native or identifier in original:
            raise ValueError("one measurement opportunity has multiple native probe records")
        time = (counter - capture.first_counter) / capture.sample_rate_hz + capture.probe_ms / 2000
        native[key] = original[identifier] = dict(probe, physical_id=identifier, time_s=time)
    return native, original


def physical_row(probe, candidate, orbit):
    return dict(
        observation_id=probe["physical_id"],
        candidate_rank=candidate["candidate_rank"],
        receiver=probe["receiver_id"],
        channel=probe["channel"],
        rf_hz=probe["actual_rf_hz"],
        counter=probe["valid_start_counter"],
        visit=probe["visit_index"],
        time_s=probe["time_s"],
        measured_cfo_hz=candidate["fractional_tracking_cfo_hz"],
        margin=candidate["fractional_margin"],
        epoch_sample=candidate["integer_epoch_sample"]
        + candidate["fractional_epoch_offset_samples"],
        norad=orbit,
    )


def bind_independent(traced, native):
    rows, identical_cfo = [], 0
    for row in traced:
        probe = native[row["receiver"], row["visit"]]
        if (probe["channel"], probe["actual_rf_hz"], probe["time_s"]) != (
            row["channel"],
            row["rf_hz"],
            row["time_s"],
        ):
            raise ValueError("anonymous decode differs from its native sample clock or RF")
        peaks = sorted(probe["candidates"], key=lambda c: c["candidate_rank"])[: stock.PEAKS]
        index = row["candidate_column"]
        if (
            not 0 <= index < len(peaks)
            or stock.fold(peaks[index]["fractional_tracking_cfo_hz"]) != row["wrapped_hz"]
        ):
            raise ValueError("the anonymous decode did not choose a native CFO peak")
        identical_cfo += (
            sum(stock.fold(p["fractional_tracking_cfo_hz"]) == row["wrapped_hz"] for p in peaks) > 1
        )
        rows.append(physical_row(probe, peaks[index], row["orbit"]))
    return rows, int(identical_cfo)
