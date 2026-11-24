"""Find at most one read-only peer nomination from original second-gate evidence."""

from collections import defaultdict
from math import isfinite, sqrt
import re


LANE_COMPONENT = re.compile(r"SCAN-RX([1-9]\d*)-CH([1-9]\d*)-T\d+-RF\d+(?:\.\d+)?")
TESTS = {"profile_rms", "profile_bias", "profile_noise", "conditional", "alias", "visibility"}
LIMITS = {"mean_z": 3.0, "slope_z": 3.0, "quadratic_bic_gain": 10.0, "maximum_step_z": 4.0}
SLOPE_ONLY = {"slope_z"}


def lane(row):
    parsed = LANE_COMPONENT.fullmatch(row["component"])
    if parsed is None:
        raise ValueError("Second screen component does not identify its original receiver and channel")
    return tuple(int(value) for value in parsed.groups())


def track_key(row):
    """Identify a witnessed active interval without guessing a missing alias."""
    return (row["component"], row["candidate_index"], row["norad"], tuple(row["observation_ids"]))


def conditional_failures(row):
    """Review the existing tests on their recorded inputs and thresholds."""
    conditional = row["conditional"]
    diag = conditional["diagnostics"]
    limits = {**LIMITS, "lag1_acf": 4 / sqrt(row["points"])}
    failures = set()
    for name, limit in limits.items():
        value = diag[name]
        if value is None or not isfinite(value):
            failures.add(name + "_unobserved")
        elif (abs(value) if name == "lag1_acf" else value) > limit:
            failures.add(name)
    rms = conditional["rms_hz"]
    if rms is None or not isfinite(rms) or rms > 450:
        failures.add("rms_hz")
    if conditional["compatible"] != (not failures):
        raise ValueError("Recorded conditional tests disagree with the pinned original gate")
    return failures


def evidence(row):
    return {key: row[key] for key in ("component", "norad", "candidate_index", "role", "observation_ids", "points")} | {
        "lane": lane(row), "failed_tests": sorted(key for key, value in row["actual_tests"].items() if value is False),
    }


def nominate(tape, *, certified_profile_slope=frozenset()):
    """Keep original dispositions and emit one deferred hypothesis only if unique.

    Certificates come from the source-bound replay of the original isolated
    gate on the identical support. This function consumes no reference owners.
    """
    if tape["screen"] != "after_salvage":
        raise ValueError("Deferred nomination requires the original second screen")
    families, assigned, seen = defaultdict(list), {}, set()
    for row in tape["tracks"]:
        identity = row["candidate_index"], row["norad"]
        previous = assigned.setdefault(identity[0], identity[1])
        tests, groups = row["actual_tests"], row["family_support_groups"]
        ids = row["observation_ids"]
        if (previous != identity[1] or row["role"] != "conditional" or set(tests) != TESTS
                or any(type(passed) is not bool for passed in tests.values())
                or type(row["compatible"]) is not bool or row["compatible"] != (all(tests.values()) and groups is None)
                or tests["conditional"] != row["conditional"]["compatible"]
                or groups is not None and (groups != 1 or not all(tests.values()))
                or len(ids) != row["points"] or len(ids) != len(set(ids)) or seen.intersection(ids)):
            raise ValueError("Original gate row no longer identifies its recorded support and disposition")
        if row["points"] < 4:
            raise ValueError("Original gate requires an identifiable curve interval")
        seen.update(ids)
        families[identity].append(row)

    closures, peers = [], []
    for rows in families.values():
        closed = [row for row in rows if row["family_support_groups"] == 1]
        if not closed:
            continue
        lanes = {lane(row) for row in closed}
        if len(lanes) != 1 or any(row["compatible"] for row in rows):
            raise ValueError("Singleton family closure disagrees with the recorded surviving lanes")
        survivor_lane, = lanes
        closure = dict(survivors=[evidence(row) for row in closed], other_lanes=[])
        closures.append(closure)
        for row in rows:
            peer_lane = lane(row)
            if peer_lane == survivor_lane:
                continue
            failed = {key for key, value in row["actual_tests"].items() if value is False}
            conditional = conditional_failures(row)
            candidate = evidence(row) | {"conditional_failures": sorted(conditional),
                                         "other_radio": peer_lane[0] != survivor_lane[0]}
            closure["other_lanes"].append(candidate)
            if conditional != SLOPE_ONLY or failed - {"conditional", "profile_noise"}:
                continue
            profile_failed = "profile_noise" in failed
            supported = not profile_failed or track_key(row) in certified_profile_slope
            candidate.update(profile_slope_known=supported,
                             profile_proof="pinned_isolated_gate" if profile_failed and supported else None)
            peers.append((closure, candidate, supported))

    if not peers:
        return dict(closures=closures, deferred=None, status="no_slope_peer" if closures else "no_family_closure")
    if len(peers) != 1:
        return dict(closures=closures, deferred=None, status="ambiguous_peer")
    closure, candidate, supported = peers[0]
    if not supported:
        return dict(closures=closures, deferred=None, status="unknown_profile_failure")
    return dict(closures=closures, deferred=dict(survivors=closure["survivors"], peer=candidate),
                status="deferred_for_independent_check")
