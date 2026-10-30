"""Major two of the graph-position result: bounded ALGO03 with ALGO02 fallback.

The first published major and its model identity remain unchanged. Scientific
audits are produced by the recovery component and admitted by a trusted runner;
this validator checks their scalar receipt and the exact published support.
"""

import math

from leo.contracts.fast_graph_position import ARMS, CENTER, KIND
from leo.contracts.fast_graph_position import validate_terminal as validate_v1

MODEL_VERSION = "algo03-causal-predictive-v1"
NAMESPACE = "fast-scan-graph-position-v2"
RF_CHECKS = (
    "paired_controls_valid",
    "exact_orbit_gates_valid",
    "incumbent_owners_preserved",
    "target_owners_verified",
    "scored_supports_only",
    "source_receipts_verified",
)


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _endpoint(arm):
    xy = arm["endpoint_east_north_km"]
    ll = arm["endpoint_latlon"]
    if (
        len(xy) != 2
        or len(ll) != 2
        or not all(_finite(v) for v in (*xy, *ll))
        or any(abs(v) > 12.5 + 1e-8 for v in xy)
    ):
        raise ValueError("Invalid ALGO03 regional endpoint")
    expected = (
        CENTER[0] + xy[1] / 111.0,
        CENTER[1] + xy[0] / (111.32 * math.cos(math.radians(CENTER[0]))),
    )
    if any(abs(a - b) > 1e-8 for a, b in zip(ll, expected, strict=True)):
        raise ValueError("ALGO03 endpoint coordinate systems disagree")
    if not _finite(arm["negative_twice_elbo"]):
        raise ValueError("Nonfinite ALGO03 frequency objective")


def validate_terminal(document, *, input_sha256):
    """Validate the immutable v2 envelope without reading storage or GPS."""
    try:
        return _validate(document, input_sha256=input_sha256)
    except (KeyError, TypeError, IndexError, OverflowError) as error:
        raise ValueError("Malformed graph-position v2 terminal") from error


def _validate(document, *, input_sha256):
    if (
        document.get("schema_version") != 2
        or document.get("kind") != KIND
        or document.get("model_version") != MODEL_VERSION
        or document.get("input_sha256") != input_sha256
        or document.get("state") not in {"complete", "unavailable", "failed"}
    ):
        raise ValueError("Graph position v2 terminal identity/state mismatch")
    if document["state"] != "complete":
        if document.get("position") is not None:
            raise ValueError("Unqualified v2 terminal cannot publish a position")
        return document
    baseline = validate_v1(document["baseline"], input_sha256=input_sha256)
    if baseline["state"] != "complete" or document["session_id"] != baseline["session_id"]:
        raise ValueError("Complete v2 inference requires its qualified recording baseline")
    if (
        document.get("reference_usage") != "none"
        or document.get("future_TLE_used") is not False
        or document.get("matched_c_inputs") is not True
        or document.get("selected_arm") != "fitted_c"
    ):
        raise ValueError("Contradictory v2 inference provenance")
    seconds = [document[k] for k in ("baseline_seconds", "recovery_seconds", "total_seconds")]
    if (
        not all(_finite(v) and v >= 0 for v in seconds)
        or seconds[0] > 1200
        or seconds[1] > 1200
        or seconds[2] > 2400
        or abs(seconds[0] + seconds[1] - seconds[2]) > 1e-6
    ):
        raise ValueError("Invalid or unbounded v2 runtime accounting")
    decision = document["decision"]
    if decision == "ALGO02_fallback":
        if document.get("selected") is not None or document["position"] != baseline["position"]:
            raise ValueError("Fallback must publish the exact ALGO02 position")
        return document
    if decision not in {"ALGO03_single", "ALGO03_joint"}:
        raise ValueError("Unknown v2 recovery decision")
    audit = document["read_audit"]
    if (
        audit.get("verified") is not True
        or audit.get("denied_paths") != []
        or audit.get("all_launched_processes_accounted") is not True
    ):
        raise ValueError("ALGO03 requires a complete clean process read audit")
    if not all(document["rf_checks"].get(check) is True for check in RF_CHECKS):
        raise ValueError("ALGO03 scientific qualification receipt incomplete")
    selected = document["selected"]
    if (decision == "ALGO03_joint" and selected["kind"] != "joint") or (
        decision == "ALGO03_single" and selected["kind"] not in {"new_family", "shared_family"}
    ):
        raise ValueError("Recovery kind and decision disagree")
    target_owners = {}
    for target in selected["targets"]:
        norad = target["norad"]
        if not isinstance(norad, int) or isinstance(norad, bool) or norad <= 0:
            raise ValueError("Invalid target satellite identity")
        for identifier in target["observation_ids"]:
            if not isinstance(identifier, str) or not identifier or identifier in target_owners:
                raise ValueError("Duplicate or invalid scored target observation")
            target_owners[identifier] = norad
    if not target_owners:
        raise ValueError("Recovery requires explicit scored target supports")
    if decision == "ALGO03_joint" and len({t["norad"] for t in selected["targets"]}) != 2:
        raise ValueError("This release supports exactly two new joint families")
    if decision == "ALGO03_single" and len({t["norad"] for t in selected["targets"]}) != 1:
        raise ValueError("Individual recovery must use one satellite family")
    pair_owners = []
    for arm in ARMS:
        saved = selected["arms"][arm]
        _endpoint(saved)
        incumbent = document["source_support"][arm]["owners"]
        if not incumbent or set(incumbent) & set(target_owners):
            raise ValueError("Targets duplicate or lack incumbent support")
        if any(
            not isinstance(i, str)
            or not i
            or not isinstance(n, int)
            or isinstance(n, bool)
            or n <= 0
            for i, n in incumbent.items()
        ):
            raise ValueError("Invalid incumbent observation ownership")
        baseline_ids = set()
        known_baseline_owners = {}
        for track in baseline["arms"][arm]["gates"]["tracks"] + baseline["arms"][arm].get(
            "linear_gates", []
        ):
            for identifier in track["observation_ids"]:
                baseline_ids.add(identifier)
                if track.get("norad") is not None:
                    if (
                        identifier in known_baseline_owners
                        and known_baseline_owners[identifier] != track["norad"]
                    ):
                        raise ValueError("Baseline observation has conflicting owners")
                    known_baseline_owners[identifier] = track["norad"]
        if baseline_ids != set(incumbent) or any(
            incumbent[i] != n for i, n in known_baseline_owners.items()
        ):
            raise ValueError("Source support differs from qualified ALGO02 terminal")
        wanted = dict(incumbent, **target_owners)
        ids = saved["associated_ids"]
        if (
            not isinstance(ids, list)
            or len(ids) != len(set(ids))
            or set(ids) != set(wanted)
            or saved["owners"] != wanted
            or saved["added_points"] != len(target_owners)
        ):
            raise ValueError("Published support differs from audited scored ownership")
        pair_owners.append(saved["owners"])
    if pair_owners[0] != pair_owners[1]:
        raise ValueError("ALGO03 c-arm observation ownership differs")
    lat, lon = selected["arms"]["fitted_c"]["endpoint_latlon"]
    if document["position"] != dict(latitude_deg=lat, longitude_deg=lon):
        raise ValueError("Published v2 position differs from selected fitted-c endpoint")
    return document
