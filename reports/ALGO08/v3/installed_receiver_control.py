"""Retain the released two-scan receiver and continuation on every admitted lane."""

from hashlib import sha256
import re


SOURCES = ("installed_receiver_control.py", "exact_named_raw.py", "full_short_raw.py", "unified_short_bootstrap.py")
RELEASE_FILE = "algo08v3-stock-detector-control.json"
RELEASE_SCHEMA = "research-algo08v3-stock-detector-control-v1"


def required(args):
    enabled = getattr(args, "installed_stock_receiver", False)
    expected = getattr(args, "assert_stock_native_sha256", None)
    if expected is not None and (not enabled or not re.fullmatch(r"sha256:[0-9a-f]{64}", expected)):
        raise ValueError("The optional stock comparison requires a tagged native SHA-256 and the installed receiver")
    return enabled


def verify_mode(args, spec):
    mixed_inputs = ("full_anchor_primary_library", "guarded_full_anchor_library", "whole_stereo_blocks", "short_lane_mask",
                    "strict_packed_eight", "packed_ci16_map", "packed_ci16_map_sha256", "packed_ci16_codec",
                    "select_before_cfo", "selective_full_20ms_recheck")
    if (not getattr(args, "verify_original_once", False) or not getattr(args, "history_risk_route", False)
            or any(getattr(args, field, None) for field in mixed_inputs)
            or spec.get("schedule", "all") != "all" or spec.get("fractional_score_selection", False)):
        raise ValueError("The exact receiver control requires original intake and the released all-visit continuation")


def recipe(spec, sources, receiver, continuation):
    return dict(receiver="installed_cancellation_factors", detector_sha256=spec["detector_sha256"],
                probe_ms=20, schedule="all", selector="installed carrier continuation in original lane order",
                receiver_source_sha256=sha256(sources[receiver]).hexdigest(),
                continuation_source_sha256=sha256(sources[continuation]).hexdigest())
