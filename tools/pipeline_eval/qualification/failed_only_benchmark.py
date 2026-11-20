"""Run unchanged compact first and retry only authenticated, diagnosed failures."""

import hashlib
import json
import os
import re
from pathlib import Path
from time import monotonic

from ..scoring import ARMS
from .deadline_benchmark import nominal_catalogue

METHOD = "v5_failed_only"
PROBE = "_compact_exception_probe"
REPAIR = "v5_causal_orbit_fit"
CAP_S = 195
GRID = "ValueError: orbit phase interpolation never extrapolates"
FAMILY = (
    "ValueError: cavity nomination failed: "
    "ValueError('family-excluded calibration phase did not converge')"
)
PREVIOUS_FRAME = re.compile(
    r'File "[^"\n]+/leo/analysis/localization_v3/orbit_modes\.py", line \d+, in previous_bank\n'
    r"[ \t]+assert good\.all\(\)[ \t]*\n(?:[ \t]+[~^]+\n)?AssertionError\Z"
)


def previous_trace(work):
    path = work / "worker.log"
    if path.is_file():
        with path.open("rb") as stream:
            stream.seek(max(0, stream.seek(0, 2) - 16384))
            return stream.read().decode(errors="replace").rstrip()
    return None


def retry_cause(row, authorized, *, previous_verified=False):
    result = row["result"]
    if (
        not authorized
        or result["status"] not in ("failed", "unavailable")
        or result["metrics"].get("candidate_s", 0) <= 0
    ):
        return None
    reason = result.get("reason")
    if reason == GRID:
        return "orbit_grid_domain"
    if reason == FAMILY:
        return "family_excluded_calibration"
    if reason == "AssertionError" and (
        previous_verified or PREVIOUS_FRAME.search(row.get("failure_trace") or "")
    ):
        return "previous_orbit_assertion"
    return None


def project(item, bulk, cache):
    from .. import corpus
    from ..variants import v5_lean

    ident = item["id"]
    if reason := item.get("unavailable"):
        return dict(id=ident, unsupported=reason)
    if (
        item["panel"] not in ("DS26", "DS29")
        or len(item["regions"]) != 1
        or tuple(item["regions"][0]["center"]) != v5_lean.ROOF_CENTER
        or item["regions"][0].get("width_km", 25.0) != v5_lean.ROOF_WIDTH_KM
        or any(
            not isinstance(item.get(k), dict)
            for k in ("native", "catalog", "track_config", "request")
        )
    ):
        return dict(
            id=ident, unsupported="complete captured factors and the original tile required"
        )
    issues = {}
    try:
        native = corpus._locate(bulk, item["native"], "native", issues)
        catalogue = corpus._locate(bulk, item["catalog"], "catalogue", issues)
        request_path = corpus._request(item, bulk, cache, native, issues)
        if native is None or catalogue is None or request_path is None:
            return dict(id=ident, unsupported=", ".join(issues.values()))
        request = json.loads(request_path.read_bytes())
        job = request["job"]
        stamp, digest, name = nominal_catalogue(request, item["cutoff_utc_ns"])
        resolved = Path(job["tle_root"]) / "archive" / "space-track" / name
        if (stamp, digest) != (item["catalog_timestamp_ns"], item["catalog"]["sha256"]) or job[
            "track_config"
        ]["sha256"].removeprefix("sha256:") != item["track_config"]["sha256"]:
            raise ValueError(
                "compact request differs from the frozen causal catalogue or track policy"
            )
        if not resolved.samefile(catalogue):
            with resolved.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                    raise ValueError("compact request resolved different catalogue bytes")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return dict(id=ident, unsupported=f"unavailable authenticated compact input: {exc}")
    binding = dict(
        id=ident,
        tile=item["regions"][0],
        native_sha256=item["native"]["sha256"],
        catalog_sha256=digest,
        track_config_sha256=item["track_config"]["sha256"],
        cutoff_utc_ns=item["cutoff_utc_ns"],
        catalogue_acquired_utc_ns=stamp,
        frozen_request_sha256=item["request"]["sha256"],
    )
    compact = dict(
        id=ident,
        panel=item["panel"],
        regions=item["regions"],
        native_path=str(native),
        native_sha256="sha256:" + binding["native_sha256"],
        request_path=str(request_path),
        session_id=item["session_id"],
    )
    return dict(id=ident, binding=binding, compact=compact)


def cases(panel, ids, cache):
    from .. import corpus

    roster, authority = corpus._selection(panel)
    if not set(ids) <= set(roster):
        raise ValueError("compact adapter cannot expose cases outside the selected corpus")
    inputs = corpus._index(corpus._read_frozen("inputs.jsonl", authority))
    bulk = Path(os.environ.get("PIPELINE_EVAL_BULK_ROOT", corpus.DEFAULT_BULK)).resolve()
    return [project(inputs[ident], bulk, cache) for ident in ids]


def run(variant, case, base, seconds, affinity, output=None):
    from ..__main__ import _input_receipt, implementation_digest, run_one

    start = monotonic()
    rows, cause = {}, None
    bound = case.get("binding")
    cap = min(seconds, CAP_S)
    if bound is None:
        result = dict(
            status="unavailable",
            reason=case["unsupported"],
            boundary="Original-budget compact v5 with targeted exception retry",
            metrics={},
            arms={arm: dict(latlon=None) for arm in ARMS},
        )
        selected = "none"
    else:
        rows["stock"] = run_one(
            PROBE, case["compact"], base, cap, affinity, output, supervised=True
        )
        cause = retry_cause(rows["stock"], True)
        selected = "repair" if cause else "stock"
        if cause:
            rows["repair"] = run_one(
                REPAIR, case["compact"], base, cap, affinity, output, supervised=True
            )
        result = rows[selected]["result"]
    elapsed = monotonic() - start
    return dict(
        id=case["id"],
        result=result,
        worker_wall_s=elapsed,
        call_s=elapsed,
        implementation_sha256=implementation_digest(variant, Path(__file__)),
        routing=dict(selected=selected, cause=cause, cap_s=cap, attempts=rows),
        **_input_receipt(bound),
    )
