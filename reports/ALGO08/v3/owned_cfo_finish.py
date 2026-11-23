"""Apply genuinely measured CFOs after the original paired roster is accepted."""

from collections import Counter
from copy import copy
from hashlib import sha256
from math import isfinite
from time import perf_counter, process_time

import numpy as np


ARMS = ("c0", "fitted_c")
CFO = "fractional_tracking_cfo_hz"
TRACKS_SHA = "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"


def identity(packet):
    return dict(packet, source={k: v for k, v in packet["source"].items()
                                if k not in ("probes", "analysis_manifest_sha256")},
                provenance={k: v for k, v in packet["provenance"].items() if k not in ("detector_sha256", "run_id")})


def views(short, refined, rule):
    if identity(short) != identity(refined):
        raise ValueError("Both views must have identical signed scope and clocks")
    cfo, positive, changed, seen = {}, {}, {}, set()
    counters = Counter()
    session = short["source"]["session_id"]
    for left, right in zip(short["source"]["probes"], refined["source"]["probes"], strict=True):
        a, b = left["candidates"], right["candidates"]
        if dict(left, candidates=[]) != dict(right, candidates=[]) or len(a) != len(b) or len(a) > 1:
            raise ValueError("Changed original opportunity or selected membership")
        rx, counter = left["receiver_id"], left["valid_start_counter"]
        oid = "sha256:" + sha256(f"{session}:{rx}:{counter}".encode()).hexdigest()
        if oid in seen:
            raise ValueError("Duplicate original receiver and hardware counter")
        seen.add(oid)
        stream = (left["edge"], left["channel"], left["actual_rf_hz"], rx)
        nonanchor = rule[counters[stream] % len(rule)] == "short_primary"
        counters[stream] += 1
        if not a:
            continue
        a, b = a[0], b[0]
        if a["passed_fractional_margin_gate"] is not True or dict(a, **{CFO: b[CFO]}) != b:
            raise ValueError("A genuine refined view can change only signed CFO")
        x, y = a[CFO], b[CFO]
        if not (isfinite(x) and isfinite(y)) or (x != y and not nonanchor):
            raise ValueError("Invalid CFO or changed full-aperture anchor")
        cfo[oid] = x
        if nonanchor:
            positive[oid] = left["visit_index"], rx
        if x != y:
            changed[oid] = y
    return cfo, positive, changed


def matching_values(track, selected, before, after, period):
    values = np.array(track["values"], dtype=float, copy=True)
    edited = set()
    for index, oid in enumerate(track["observation_ids"]):
        if oid not in selected:
            continue
        lift = round((values[index] - before[oid])/period)
        if values[index] != before[oid] + lift * period:
            raise ValueError("The selected track is inconsistent with its measured CFO and original alias lift")
        values[index] = after[oid] + lift * period
        edited.add(oid)
    return values, edited


def revised_inputs(prepared, incumbent, selected, before, after, period):
    scan = copy(incumbent["scan"])
    scan.reference, scan.element_derivatives = dict(scan.reference), dict(scan.element_derivatives)
    scan.tracks = list(scan.tracks)
    edited = set()
    by_key = {}
    for index, track in enumerate(scan.tracks):
        if selected.intersection(track["observation_ids"]):
            values, rows = matching_values(track, selected, before, after, period)
            if edited & rows:
                raise ValueError("A refined owner maps to more than one original graph row")
            edited |= rows
            scan.tracks[index] = dict(track, values=values)
            by_key[track["key"]] = scan.tracks[index]
    if edited != selected:
        raise ValueError("A refined owner is missing from the accepted graph")
    scan.groups = [(key, [by_key.get(track["key"], track) for track in rows]) for key, rows in scan.groups]
    old = prepared["tracks"]
    observations = [dict(row, measured_cfo_hz=after[row["observation_id"]]) if row["observation_id"] in selected else row
                    for row in old["observations"]]
    if sum(row["observation_id"] in selected for row in observations) != len(selected):
        raise ValueError("A refined owner is missing from the evidence observations")
    return dict(prepared, tracks=dict(old, tracks=scan.tracks, observations=observations)), dict(incumbent, scan=scan)


class OwnedCfo:
    def __init__(self, native, refined, rule):
        self.native = native
        self.before, self.positives, self.refined = views(native, refined, rule)
        self.period = None
        self.notes = {}
        self.evidence = []

    def bind(self, native, assets):
        from aperture_trial import read

        if native != self.native or self.period is not None:
            raise ValueError("Expected one original short-view scientific handoff")
        path = assets / "tracks.json"
        if sha256(path.read_bytes()).hexdigest() != TRACKS_SHA:
            raise ValueError("The released integral alias period must be pinned")
        self.period = float(read(path)["config"]["alias_spacing_hz"])

    def prepare(self, original, native, *args, **kwargs):
        return original(native, *args, **kwargs)

    def repair(self, prepared, incumbent, measured):
        from blind_joint_finish import elapsed
        from local_future_repair import memberships
        from leo.analysis.localization_v3.event_position import refit
        from leo.analysis.localization_v3.history_policy import pair_passes

        start = process_time(), perf_counter()
        notes = self.notes = measured["local_future_repair"] = {"kind": "owned archived CFO", "decision": "unchanged"}
        try:
            owned = memberships(incumbent, "c0")
            if owned != memberships(incumbent, "fitted_c"):
                raise ValueError("Original arms disagree in paired fixed ownership")
            ids = set().union(*(rows for _, _, rows in owned.values()))
            selected = ids & self.refined.keys()
            notes.update(original_owners=len(ids), owned_positive_shorts=len(ids & self.positives.keys()),
                         archive_refined_owners=len(selected), ids=sorted(selected))
            if not selected:
                return prepared, incumbent
            new_prepared, trial = revised_inputs(prepared, incumbent, selected, self.before, self.refined, self.period)
            notes["replacement_clocks"] = elapsed(*start)
            trial["arms"] = {}
            notes["restored_original_fit"] = {}
            for arm in ARMS:
                started = process_time(), perf_counter()
                try:
                    trial["arms"][arm] = refit(trial["scan"], trial["node"], trial["keep"], arm,
                                                trial["powers"], trial["means"], trial["model"], [], trial["entries"])
                finally:
                    notes["restored_original_fit"][arm] = elapsed(*started)
            notes["pair_passes"] = pair_passes(trial["arms"], include_linear=bool(trial["entries"]),
                                               half_width_km=trial["scan"].search_region.half_width_km)
            if not notes["pair_passes"] or any(memberships(trial, arm) != owned for arm in ARMS):
                notes.update(decision="rejected", reason="original paired compatibility or fixed ownership")
                return prepared, incumbent
            notes["decision"] = "proposed"
            return new_prepared, trial
        except (ValueError, AssertionError, np.linalg.LinAlgError) as exc:
            notes.update(decision="rejected", reason=f"{type(exc).__name__}: {exc}")
            return prepared, incumbent
        finally:
            notes["owned_update_total"] = elapsed(*start)

    def emitted(self, packet):
        raw = {}
        for arm, rows in packet["rows"].items():
            measurements = {row["observation_id"]: row["measured_cfo_hz"] for row in rows}
            if any(hz not in (self.before[oid], self.refined.get(oid, self.before[oid])) for oid, hz in measurements.items()):
                raise ValueError("Evidence contains an unbound CFO")
            raw[arm] = sorted(oid for oid, hz in measurements.items() if hz != self.before[oid])
        self.evidence.append(raw)
        return packet
