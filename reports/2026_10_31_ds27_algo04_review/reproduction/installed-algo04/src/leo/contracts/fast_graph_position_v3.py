"""ALGO04's separate persisted major preserves the published ALGO03 incumbent."""

import math

from leo.contracts.fast_graph_position import ARMS, KIND
from leo.contracts.fast_graph_position_v2 import validate_terminal as validate_v2

MODEL_VERSION = "algo04-causal-numerical-v1"
NAMESPACE = "fast-scan-graph-position-v3"


def published_owners(terminal, arm):
    """Read explicit published ALGO03 owners through its public proof envelope."""
    if terminal.get("selected"):
        owners = terminal["selected"]["arms"][arm]["owners"]
    else:
        known = {}
        baseline_ids = set()
        saved = terminal["baseline"]["arms"][arm]
        for track in saved["gates"]["tracks"] + saved.get("linear_gates", []):
            norad = track.get("norad")
            for identifier in track["observation_ids"]:
                baseline_ids.add(identifier)
                if identifier in known and known[identifier] != norad:
                    raise ValueError("Conflicting incumbent observation owners")
                if norad is not None:
                    known[identifier] = norad
        owners = (
            terminal["source_support"][arm]["owners"] if terminal.get("source_support") else known
        )
        if set(owners) != baseline_ids or any(owners[i] != n for i, n in known.items()):
            raise ValueError("Incumbent ownership does not match its published baseline")
    if not owners or any(
        not isinstance(i, str) or not i or not isinstance(n, int) or isinstance(n, bool) or n <= 0
        for i, n in owners.items()
    ):
        raise ValueError("Missing valid explicit incumbent observation ownership")
    return owners


def candidate_admission(incumbent, candidate):
    """Pure additive acceptance over already validated v2 proof envelopes."""
    if candidate is None or candidate.get("state") != "complete" or not candidate.get("selected"):
        return False, "no_qualified_numerical_candidate"
    if (incumbent.get("read_audit") or {}).get("verified") is not True:
        return False, "historical_incumbent_read_audit_not_verified"
    try:
        for arm in ARMS:
            old = published_owners(incumbent, arm)
            new = candidate["selected"]["arms"][arm]["owners"]
            if any(new.get(identifier) != norad for identifier, norad in old.items()):
                return False, "would_lose_or_change_published_ALGO03_owner"
    except (KeyError, TypeError, ValueError):
        return False, "incumbent_ownership_not_provable"
    return True, "paired_qualified_candidate_preserves_published_ALGO03_owners"


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_terminal(document, *, input_sha256):
    """Validate major three without modifying the published v1 or v2 contracts."""
    try:
        return _validate(document, input_sha256=input_sha256)
    except (KeyError, TypeError, IndexError, OverflowError) as error:
        raise ValueError("Malformed graph-position v3 terminal") from error


def _validate(document, *, input_sha256):
    if (
        document.get("schema_version") != 3
        or document.get("kind") != KIND
        or document.get("model_version") != MODEL_VERSION
        or document.get("input_sha256") != input_sha256
        or document.get("state") not in {"complete", "unavailable", "failed"}
    ):
        raise ValueError("Graph position v3 terminal identity/state mismatch")
    if document["state"] != "complete":
        if document.get("position") is not None:
            raise ValueError("Unqualified v3 terminal cannot publish a position")
        return document
    incumbent = validate_v2(document["incumbent"], input_sha256=input_sha256)
    if incumbent["state"] != "complete" or document["session_id"] != incumbent["session_id"]:
        raise ValueError("ALGO04 requires its qualified published ALGO03 recording incumbent")
    if (
        document.get("reference_usage") != "none"
        or document.get("future_TLE_used") is not False
        or document.get("matched_c_inputs") is not True
        or document.get("selected_arm") != "fitted_c"
    ):
        raise ValueError("Contradictory v3 inference provenance")
    seconds = [document[k] for k in ("incumbent_seconds", "numerical_seconds", "total_seconds")]
    if (
        not all(_finite(v) and v >= 0 for v in seconds)
        or seconds[0] != incumbent["total_seconds"]
        or seconds[1] > 1200
        or seconds[2] > 3600
        or abs(seconds[0] + seconds[1] - seconds[2]) > 1e-6
    ):
        raise ValueError("Invalid or unbounded v3 runtime accounting")
    candidate = document.get("candidate")
    if candidate is not None:
        validate_v2(candidate, input_sha256=input_sha256)
        if (
            candidate["state"] != "complete"
            or candidate["session_id"] != incumbent["session_id"]
            or candidate["baseline"] != incumbent["baseline"]
        ):
            raise ValueError(
                "Numerical candidate does not share the exact ALGO03 input and ALGO02 baseline"
            )
    if document["decision"] == "ALGO03_fallback":
        if document["position"] != incumbent["position"]:
            raise ValueError("Fallback must publish the exact ALGO03 incumbent position")
        return document
    if document["decision"] != "ALGO04_additive":
        raise ValueError("Unknown v3 numerical decision")
    admitted, reason = candidate_admission(incumbent, candidate)
    if not admitted:
        raise ValueError("ALGO04 candidate rejected: " + reason)
    if document["position"] != candidate["position"]:
        raise ValueError("ALGO04 position differs from its chosen fitted-c candidate endpoint")
    return document
