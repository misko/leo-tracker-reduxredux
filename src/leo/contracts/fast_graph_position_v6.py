"""ALGO07: guarded causal reassociation over an unchanged ALGO06 incumbent."""

import hashlib
import json
import math

from leo.contracts.fast_graph_position import ARMS, KIND
from leo.contracts.fast_graph_position_v5 import owners as v5_incumbent_owners
from leo.contracts.fast_graph_position_v5 import validate_terminal as validate_previous

MODEL_VERSION = "algo07-causal-guarded-reassociation-v1"
NAMESPACE = "fast-scan-graph-position-v6"
POLICY = "causal-reassociation-unique-receiver-groups-v1"


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def incumbent_owners(terminal):
    """Read ALGO06 output owners; v5's helper reads its v4 incumbent owners."""
    if terminal["decision"] == "ALGO06_additive":
        return {a: dict(terminal["candidate"]["published_owners"][a]) for a in ARMS}
    return v5_incumbent_owners(terminal["incumbent"])


def owners(terminal):
    if terminal["decision"] == "ALGO07_reassociation":
        return {a: dict(terminal["candidate"]["published_owners"][a]) for a in ARMS}
    return incumbent_owners(terminal["incumbent"])


def _ids(values):
    if (
        not isinstance(values, list)
        or any(not isinstance(v, str) or not v for v in values)
        or len(values) != len(set(values))
    ):
        raise ValueError("Native observation IDs must be unique nonempty strings")
    return set(values)


def _norad(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _same_number(actual, expected):
    return finite(actual) and finite(expected) and abs(actual - expected) <= 1e-8


def _fit(row):
    for key in (
        "qualified",
        "all_gates_pass",
        "phase_closed",
        "optimizer_success",
        "mixture_phase_interior",
        "mixture_gates_pass",
    ):
        if row.get(key) is not True:
            raise ValueError("Physical fit gate failed: " + key)
    if row.get("status") != "complete" or not finite(row["objective"]) or row.get("failed_gates"):
        raise ValueError("Incomplete physical fit")
    if (
        row.get("lost_ids")
        or row.get("lost_ids_count", 0)
        or row.get("unexpected_reassigned_ids")
        or row.get("unexpected_reassigned_ids_count", 0)
    ):
        raise ValueError("Native ownership violation")
    last = row["history"][-1]
    if (
        last["success"] is not True
        or not finite(last["phase_change_s"])
        or not 0 <= last["phase_change_s"] <= 0.01
    ):
        raise ValueError("Phase or optimizer failed to converge")
    if not row["exact"] or any(r["all_pass"] is not True or r.get("failed") for r in row["exact"]):
        raise ValueError("Exact orbit gates failed")
    masses = row["phase_boundary_masses"]
    if not isinstance(masses, list) or any(not finite(v) or not 0 <= v < 0.01 for v in masses):
        raise ValueError("Mixture phase boundary mass failed")
    lat, lon = row["endpoint_latlon"]
    if not finite(lat) or not finite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("Invalid endpoint position")
    ids = [oid for track in row["tracks"] for oid in track["observation_ids"]]
    _ids(ids)
    if not ids:
        raise ValueError("Native fit evidence missing")
    digest = hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()
    if row["native_ids_sha256"] != digest:
        raise ValueError("Native fit hash differs from raw tracks")
    proposed = row["proposed_owners"]
    if not isinstance(proposed, dict) or any(
        not isinstance(k, str) or not k or not _norad(v) for k, v in proposed.items()
    ):
        raise ValueError("Invalid proposed native owners")
    if (
        row.get("owners_sha256")
        != hashlib.sha256(json.dumps(proposed, sort_keys=True).encode()).hexdigest()
    ):
        raise ValueError("Owner hash differs from raw ownership")
    if any(
        not _norad(track["norad"])
        or any(proposed.get(oid) != track["norad"] for oid in track["observation_ids"])
        for track in row["tracks"]
    ):
        raise ValueError("Raw tracks differ from proposed ownership")
    return set(ids)


def _guard(g, old, new):
    candidates = g["candidates"]
    if (
        not isinstance(candidates, list)
        or len(candidates) != len(set(candidates))
        or any(not _norad(v) for v in candidates)
        or not {old, new} <= set(candidates)
        or g["proposed"] != new
        or g["passed"] is not True
        or g["status"] != "passed"
        or g["model"] != "receiver_offset"
        or g["phase_sd_s"] != 5.0
        or g["minimum_unique_folds"] != 5
        or g["required_minimum_margin_exclusive"] != 0.0
        or g["missing"]
        or not isinstance(g["unique_folds"], int)
        or not 5 <= g["unique_folds"] <= 10
        or g["total_partitions"] != g["unique_folds"]
    ):
        raise ValueError("Incomplete frozen predictive uniqueness guard")
    folds = g["retained_fold_ids"]
    if len(folds) != g["unique_folds"] or len(set(folds)) != len(folds):
        raise ValueError("Repeated predictive fold identity")
    expected = {(a, n) for a in ARMS for n in candidates if n != new}
    rows = g["competitors"]
    if len(rows) != len(expected) or {(r["arm"], r["norad"]) for r in rows} != expected:
        raise ValueError("Every predictive competitor must be checked in both arms")
    minima = []
    for row in rows:
        margins = row["margins"]
        if (
            len(margins) != len(folds)
            or any(not finite(v) or v <= 0 for v in margins)
            or row["folds"] != len(folds)
            or row["wins"] != len(folds)
            or not _same_number(row["minimum_margin"], min(margins))
            or not _same_number(row["mean_margin"], sum(margins) / len(margins))
        ):
            raise ValueError("Predictive competitor does not win every unique fold")
        minima.append(min(margins))
    if not _same_number(g["minimum_margin"], min(minima)):
        raise ValueError("Predictive minimum margin differs from full competition")


def validate_terminal(doc, *, input_sha256):
    try:
        return _validate(doc, input_sha256)
    except (KeyError, TypeError, IndexError, OverflowError, AttributeError) as exc:
        raise ValueError("Malformed v6 terminal") from exc


def _validate(d, sha):
    if (
        d.get("schema_version") != 6
        or d.get("kind") != KIND
        or d.get("model_version") != MODEL_VERSION
        or d.get("input_sha256") != sha
        or d.get("state") not in ("complete", "failed", "unavailable")
    ):
        raise ValueError("Graph position v6 identity mismatch")
    if d["state"] != "complete":
        if d.get("position") is not None:
            raise ValueError("Unqualified position")
        return d
    old = validate_previous(d["incumbent"], input_sha256=sha)
    if old["state"] != "complete" or old["session_id"] != d["session_id"]:
        raise ValueError("Wrong ALGO06 incumbent")
    if (
        d.get("reference_usage") != "none"
        or d.get("future_TLE_used") is not False
        or d.get("matched_c_inputs") is not True
        or d.get("selected_arm") != "fitted_c"
        or d.get("recovery_policy") != POLICY
    ):
        raise ValueError("Contradictory inference provenance")
    times = [d[k] for k in ("incumbent_seconds", "recovery_seconds", "total_seconds")]
    if (
        any(not finite(t) or t < 0 for t in times)
        or times[0] != old["total_seconds"]
        or times[1] > 1200
        or times[2] > 7200
        or abs(times[0] + times[1] - times[2]) > 1e-6
    ):
        raise ValueError("Invalid runtime accounting")
    if d["decision"] == "ALGO06_fallback":
        if d.get("candidate") is not None or d["position"] != old["position"]:
            raise ValueError("Fallback must preserve exact ALGO06 position")
        return d
    if (
        d["decision"] != "ALGO07_reassociation"
        or (d.get("read_audit") or {}).get("verified") is not True
    ):
        raise ValueError("Missing guarded reassociation proof")
    c = d["candidate"]
    if c["policy"] != POLICY:
        raise ValueError("Wrong frozen reassociation policy")
    source, destination = c["old_norad"], c["new_norad"]
    if not _norad(source) or not _norad(destination) or source == destination:
        raise ValueError("Reassociation requires distinct satellite identities")
    prior = incumbent_owners(old)
    targets = _ids(c["target_ids"])
    universe = _ids(c["observation_ids"])
    if not targets or any(destination in values.values() for values in prior.values()):
        raise ValueError("Reassociation destination must be previously unowned")
    cutoff = c["cutoff_utc_ns"]
    if not isinstance(cutoff, int) or isinstance(cutoff, bool) or cutoff <= 0:
        raise ValueError("Explicit scan cutoff required")
    for key in ("element_epoch_utc_ns", "collected_utc_ns"):
        value = c["element"][key]
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or not 0 <= cutoff - value <= 72 * 3600 * 10**9
        ):
            raise ValueError("Noncausal or over-age replacement element")
    record = c["record"]
    h = record["hypothesis"]
    if (
        record["accepted"] is not True
        or record["target"] != source
        or h["norad"] != destination
        or record["name"] != h["name"]
        or set(h["allowed_families"]) != {source, destination}
        or not h["mapping"]
        or set(h["mapping"].values()) != {destination}
    ):
        raise ValueError("Record differs from whole-family replacement hypothesis")
    count = c["shortlist_count"]
    if (
        not isinstance(count, int)
        or isinstance(count, bool)
        or count < 2
        or count != len(c["guard"]["candidates"])
    ):
        raise ValueError("Full common shortlist required")
    penalty = 2 * math.log(max(2, count))
    if not _same_number(h["penalty"], penalty):
        raise ValueError("Frozen shortlist penalty differs")
    _guard(c["guard"], source, destination)
    for arm in ARMS:
        predictive = h["predictive"][arm]
        gains = predictive["gains"]
        if (
            len(gains) != 5
            or any(not finite(v) for v in gains)
            or not _same_number(predictive["mean"], sum(gains) / 5)
            or predictive["mean"] <= 0
            or predictive["wins"] != sum(v > 0 for v in gains)
            or predictive["wins"] < 4
            or predictive["pass_check"] is not True
        ):
            raise ValueError("Inherited five-fold predictive admission failed")
        trial, control = record["pair"][arm], record["control"][arm]
        native = _fit(trial)
        if native != _fit(control) or trial["native_ids_sha256"] != control["native_ids_sha256"]:
            raise ValueError("Matched native c-arm control evidence differs")
        family_components = {
            track["component"] for track in control["tracks"] if track["norad"] == source
        }
        trial_components = {track["component"] for track in trial["tracks"]}
        if (
            set(h["mapping"]) != family_components
            or not family_components <= trial_components
            or any(
                track["norad"] != destination
                for track in trial["tracks"]
                if track["component"] in family_components
            )
        ):
            raise ValueError("Hypothesis must replace the complete native satellite family")
        if not native <= universe or not set(prior[arm]) <= universe:
            raise ValueError("Unknown native observations")
        expected = {oid: trial["proposed_owners"][oid] for oid in prior[arm]}
        changed = {oid for oid in prior[arm] if expected[oid] != prior[arm][oid]}
        if (
            changed != targets
            or any(prior[arm][oid] != source or expected[oid] != destination for oid in changed)
            or c["published_owners"][arm] != expected
        ):
            raise ValueError("Published ownership must be an exact guarded reassociation")
        if any(control["proposed_owners"].get(oid) != owner for oid, owner in prior[arm].items()):
            raise ValueError("Control changed published incumbent ownership")
        if set(trial["reassigned_ids"]) & set(prior[arm]) != targets:
            raise ValueError("Raw reassignment IDs differ from published changes")
        scores = (
            control["objective"],
            c["baseline_objectives"][arm],
            record["matched_published_objectives"][arm],
        )
        if any(not finite(value) for value in scores):
            raise ValueError("Nonfinite matched score bound")
        bound = min(scores)
        gain = bound - trial["objective"] - penalty
        if (
            not _same_number(record["bounds"][arm], bound)
            or not finite(gain)
            or gain <= 0
            or not _same_number(record["gains"][arm], gain)
        ):
            raise ValueError("Paired frozen score bounds or penalized gains failed")
        if c["arms"][arm]["endpoint_latlon"] != trial["endpoint_latlon"]:
            raise ValueError("Selected arm differs from qualified physical fit")
    expected_position = dict(
        zip(
            ("latitude_deg", "longitude_deg"),
            c["arms"]["fitted_c"]["endpoint_latlon"],
            strict=True,
        )
    )
    if d["position"] != expected_position:
        raise ValueError("Position differs from selected fitted-c arm")
    return d
