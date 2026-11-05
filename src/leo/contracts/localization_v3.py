"""Version-one standalone result receipt; older ALGO contracts are unchanged."""

import math
import re

from leo.contracts.digests import canonical_digest
from leo.contracts.fast_standard_analysis import MODEL as POLICY_MODEL

MODEL = "algo07v3-exact-v1"
ARMS = ("c0", "fitted_c")


def validate_evidence(evidence):
    """Cross-check scientific ownership and presentation before making it visible."""
    try:
        if (
            evidence["schema_version"] != 1
            or evidence["model_version"] != MODEL
            or evidence["status"] != "figures_ready"
        ):
            raise ValueError("Completed standalone evidence required")
        validate_identity(evidence["identity"])
        for key in ("configuration_sha256", "implementation_sha256"):
            require_digest(evidence["provenance"][key])
        final = evidence["audit"]["reassociation_complete"]
        if final["status"] != "reassociation_evaluated" or final["recovery_complete"] is not True:
            raise ValueError("Completed final recovery required")
        packet = evidence["presentation"]
        native = packet["observations"]
        ids = {o["observation_id"] for o in native}
        if not native or len(ids) != len(native):
            raise ValueError("Unique native observations required")
        selected = evidence["selected"]
        if set(selected["owners"]) != set(ARMS) or set(packet["arms"]) != set(ARMS):
            raise ValueError("Both selected calibration arms required")
        for arm in ARMS:
            owners = selected["owners"][arm]
            summary = packet["arms"][arm]
            rows = packet["rows"][arm]
            predicted = {r["observation_id"]: r["norad"] for r in rows}
            if (
                not set(owners) <= ids
                or any(type(n) is not int or n <= 0 for n in owners.values())
                or len(predicted) != len(rows)
                or predicted != owners
                or summary["associated_points"] != len(owners)
                or summary["owner_sha256"] != canonical_digest(owners)
                or list(selected["arms"][arm]["endpoint_latlon"]) != summary["endpoint_latlon"]
                or len(owners) != final["recovery"]["final"][arm]["associated"]
            ):
                raise ValueError("Selected science and presentation ownership/position differ")
        if evidence["render"]["reference_usage"] != "evaluation_only":
            raise ValueError("Evaluation reference must be presentation-only")
        return evidence
    except (KeyError, TypeError) as error:
        raise ValueError("Malformed standalone evidence") from error


def require_digest(value):
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise ValueError("A content-bound SHA-256 digest is required")


def validate_identity(identity):
    if set(identity) != {"run_id", "session_id", "input_sha256"}:
        raise ValueError("Explicit native run, session and input binding required")
    for name in ("run_id", "session_id"):
        if not isinstance(identity[name], str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", identity[name]
        ):
            raise ValueError("Invalid localization identity")
    require_digest(identity["input_sha256"])


def validate(receipt):
    try:
        if (
            receipt["schema_version"] != 1
            or receipt["model_version"] != MODEL
            or receipt["policy_model_version"] != POLICY_MODEL
            or receipt["state"] != "complete"
        ):
            raise ValueError("Invalid standalone result version/state")
        validate_identity({k: receipt[k] for k in ("run_id", "session_id", "input_sha256")})
        require_digest(receipt["result_sha256"])
        if type(receipt["result_bytes"]) is not int or receipt["result_bytes"] <= 0:
            raise ValueError("Invalid result size")
        if type(receipt["glrt_points"]) is not int or receipt["glrt_points"] < 1:
            raise ValueError("Invalid native point count")
        if set(receipt["arms"]) != set(ARMS):
            raise ValueError("Both calibration arms required")
        for arm in receipt["arms"].values():
            latlon = arm["endpoint_latlon"]
            if (
                len(latlon) != 2
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in latlon)
                or not -90 <= latlon[0] <= 90
                or not -180 <= latlon[1] <= 180
            ):
                raise ValueError("Invalid result endpoint")
            if (
                type(arm["associated_points"]) is not int
                or not 0 <= arm["associated_points"] <= receipt["glrt_points"]
            ):
                raise ValueError("Invalid result ownership count")
            require_digest(arm["owner_sha256"])
        return receipt
    except (KeyError, TypeError) as error:
        raise ValueError("Malformed standalone result receipt") from error
