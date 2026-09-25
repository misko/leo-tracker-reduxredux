#!/usr/bin/env python3
"""Fail-closed publication policy for DS3 geometry position projections."""

from __future__ import annotations

from typing import Any

GEOMETRY_DIAGNOSTIC_STATUS = "geometry_position_diagnostic"


def explicit_qualification_gate(value: dict[str, Any]) -> bool:
    """Accept only an explicit, fully passed gate from a sealed projection.

    A bare ``terminal_status=qualified`` or ``qualified=true`` is not a gate.
    The gate must name nonempty boolean criteria, pass all of them, and retain
    the reference/held-data separation required by the DS3 report.
    """

    gate = value.get("qualification_gate")
    if not isinstance(gate, dict) or gate.get("passed") is not True:
        return False
    criteria = gate.get("criteria")
    if not isinstance(criteria, dict) or not criteria:
        return False
    if not all(isinstance(item, bool) and item for item in criteria.values()):
        return False
    return (
        value.get("reference_used_for_inference") is False
        and value.get("held_used_for_selection") is False
    )


def effective_scope(
    projection: dict[str, Any], source: dict[str, Any]
) -> dict[str, Any]:
    """Derive the geometry subset and support without using truth coordinates."""

    session_ids = sorted(
        {
            str(session_id)
            for row in source.get("results", [])
            if isinstance(row, dict)
            for session_id in row.get("session_ids", [])
        }
    )
    support = projection.get("support")
    support = support if isinstance(support, dict) else {}
    session_count = len(session_ids)
    reported_count = support.get("geometry_valid_sessions")
    if isinstance(reported_count, int) and session_count and reported_count != session_count:
        raise ValueError("geometry session-count provenance mismatch")
    if not session_count and isinstance(reported_count, int):
        session_count = reported_count
    return {
        "dataset": "DS3",
        "scope": "geometry_eligible_subset",
        "label": f"DS3/geometry{session_count}",
        "session_count": session_count,
        "session_ids": session_ids,
        "supported_tracks": support.get("supported_tracks"),
        "unsupported_tracks": support.get("unsupported_tracks"),
        "supported_occupied_second_fraction": support.get(
            "supported_occupied_second_fraction"
        ),
    }


def publication_metadata(
    projection: dict[str, Any], source: dict[str, Any]
) -> dict[str, Any]:
    gated = explicit_qualification_gate(projection)
    return {
        "terminal_status": "qualified" if gated else GEOMETRY_DIAGNOSTIC_STATUS,
        "ranking_eligible": gated,
        "qualification_gate_present": gated,
        "qualification_reason": (
            "explicit sealed geometry qualification gate passed"
            if gated
            else "geometry projection has no explicit sealed qualification gate"
        ),
        "effective_scope": effective_scope(projection, source),
    }
