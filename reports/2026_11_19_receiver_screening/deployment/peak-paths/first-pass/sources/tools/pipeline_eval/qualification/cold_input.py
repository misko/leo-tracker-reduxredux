"""Blind input port for a receiver starting at GLRT candidates and causal orbital elements."""

import json
import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .full_v5_check import BULK, _load_case

PROBE_FIELDS = (
    "actual_rf_hz",
    "channel",
    "edge",
    "payload_start_sample",
    "probe_index",
    "probe_start_ms",
    "receiver_id",
    "valid_start_counter",
    "visit_index",
)
CANDIDATE_FIELDS = (
    "candidate_rank",
    "integer_epoch_sample",
    "fractional_epoch_offset_samples",
    "fractional_tracking_cfo_hz",
    "fractional_exact_score",
    "fractional_control_score",
    "fractional_margin",
    "passed_fractional_margin_gate",
)


@dataclass(frozen=True)
class NativeCapture:
    case_id: str
    probes: list[dict]
    sample_rate_hz: int
    probe_ms: int
    first_counter: int
    anchor_utc_ns: int
    cutoff_utc_ns: int
    catalog_timestamp_ns: int
    duration_s: float
    catalog: bytes
    native_sha256: str
    catalog_sha256: str


def _verified(bulk, locator):
    raw = (bulk / locator["path"]).read_bytes()
    if sha256(raw).hexdigest() != locator["sha256"]:
        raise ValueError("receiver input differs from its frozen digest")
    return raw


def load(case_id):
    case = _load_case(case_id)
    native, catalog = case.get("native"), case.get("catalog")
    if not isinstance(native, dict) or not isinstance(catalog, dict):
        raise FileNotFoundError("This case lacks frozen GLRT candidate probes and causal TLE input")
    bulk = Path(os.environ.get("PIPELINE_EVAL_BULK_ROOT", BULK)).resolve()
    document = json.loads(_verified(bulk, native))
    source, anchor = document["source"], document["clock_anchor"]
    before, after = (anchor[k]["realtime_ns"] for k in ("before", "after"))
    first = anchor["sample_counter"]
    if (
        not source["qualified"]
        or source["session_id"] != case["session_id"]
        or before != case["cutoff_utc_ns"]
        or before > after
        or case["catalog_timestamp_ns"] > before
        or document["last_sample_counter"] <= first
        or source["sample_rate_hz"] <= 0
    ):
        raise ValueError("unqualified GLRT acquisition, clock bracket or future catalogue")
    probes = [
        {
            **{k: p[k] for k in PROBE_FIELDS},
            "candidates": [{k: c[k] for k in CANDIDATE_FIELDS} for c in p["candidates"]],
        }
        for p in source["probes"]
    ]
    return NativeCapture(
        case_id=case_id,
        probes=probes,
        sample_rate_hz=source["sample_rate_hz"],
        probe_ms=source["probe_ms"],
        first_counter=first,
        anchor_utc_ns=(before + after) // 2,
        cutoff_utc_ns=before,
        catalog_timestamp_ns=case["catalog_timestamp_ns"],
        duration_s=(document["last_sample_counter"] - first) / source["sample_rate_hz"],
        catalog=_verified(bulk, catalog),
        native_sha256=native["sha256"],
        catalog_sha256=catalog["sha256"],
    )


def matched_offers(case_id):
    """Explicit optional tile for the measured prior-assisted comparison."""
    return _load_case(case_id)["regions"]
