"""Bind and supervise the opt-in compact then smooth-clock benchmark."""

import hashlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from time import monotonic

from ..scoring import ARMS
from ..variants import deadline_receiver as policy

COMPACT = "v5_secant_fit"
SMOOTH = "portable_native_clock"
SOLVER_EXCEPTIONS = ("ValueError:", "AssertionError:", "ArithmeticError:")
SHARED = (
    "native_sha256",
    "catalog_sha256",
    "track_config_sha256",
    "capture_utc_ns",
    "cutoff_utc_ns",
    "catalogue_acquired_utc_ns",
    "tile",
)


def nominal_catalogue(request, cutoff):
    choices = []
    for name, expected in request["causal_snapshots"].items():
        raw_stamp = name.split("-", maxsplit=1)[0]
        stamp, digest = int(raw_stamp), expected.removeprefix("sha256:")
        if (
            not 0 < stamp <= cutoff
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
            or f"{stamp}-{digest}.tle" != name
        ):
            raise ValueError("compact v5 request contains a malformed or future catalogue")
        if stamp < cutoff:
            choices.append((stamp, digest, name))
    if not choices:
        raise ValueError("compact v5 request has no prior causal catalogue")
    latest = max(stamp for stamp, _, _ in choices)
    matches = [row for row in choices if row[0] == latest]
    if len(matches) != 1:
        raise ValueError("compact v5 request has an ambiguous latest catalogue")
    return matches[0]


def project(item, bulk, cache):
    from .. import corpus
    from ..variants import lean_receiver_cli_benchmark as native
    from ..variants import v5_lean

    ident = item["id"]
    if (
        item["panel"] not in ("DS26", "DS29")
        or len(item["regions"]) != 1
        or tuple(item["regions"][0]["center"]) != v5_lean.ROOF_CENTER
        or item["regions"][0].get("width_km", 25.0) != v5_lean.ROOF_WIDTH_KM
        or not item.get("request")
        or not item.get("session_id")
    ):
        return dict(id=ident, unsupported="a frozen compact v5 request and original tile required")
    smooth = native.project(item, bulk)
    if "unsupported" in smooth:
        return smooth

    issues = {}
    try:
        native.lean.interface(
            smooth["offer"],
            smooth["capture"],
            smooth["cutoff"],
            smooth["catalogue_acquired"],
            smooth["probe_limit"],
        )
        request_path = corpus._request(item, bulk, cache, Path(smooth["files"]["native"]), issues)
        if request_path is None:
            return dict(id=ident, unsupported=", ".join(issues.values()))
        request = json.loads(request_path.read_bytes())
        job, expected = request["job"], smooth["expected"]
        stamp, digest, filename = nominal_catalogue(request, smooth["cutoff"])
        if (
            (stamp, digest) != (smooth["catalogue_acquired"], expected["catalogue"])
            or job["evaluation_reference"] is not None
            or job["search_center"] != smooth["offer"]["center"]
            or job["native_input"]["sha256"].removeprefix("sha256:") != expected["native"]
            or job["track_config"]["sha256"].removeprefix("sha256:") != expected["track_config"]
            or not Path(job["track_config"]["path"]).samefile(smooth["files"]["track_config"])
        ):
            raise ValueError("compact and smooth-clock requests differ in their causal inputs")
        catalogue = Path(job["tle_root"]) / "archive" / "space-track" / filename
        if not catalogue.samefile(smooth["files"]["catalogue"]):
            with catalogue.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                    raise ValueError("compact and smooth-clock catalogue bytes differ")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return dict(id=ident, unsupported=f"unavailable shared deadline input: {exc}")

    binding = dict(
        id=ident,
        native_sha256=expected["native"],
        catalog_sha256=digest,
        track_config_sha256=expected["track_config"],
        capture_utc_ns=smooth["capture"],
        cutoff_utc_ns=smooth["cutoff"],
        catalogue_acquired_utc_ns=stamp,
        tile=smooth["offer"],
        frozen_request_sha256=item["request"]["sha256"],
    )
    compact = dict(
        id=ident,
        panel=item["panel"],
        regions=[smooth["offer"]],
        native_path=smooth["files"]["native"],
        native_sha256="sha256:" + expected["native"],
        request_path=str(request_path),
        session_id=item["session_id"],
    )
    return dict(id=ident, binding=binding, compact=compact, smooth=smooth)


def cases(panel, ids, cache):
    from .. import corpus

    roster, authority = corpus._selection(panel)
    inputs = corpus._index(corpus._read_frozen("inputs.jsonl", authority))
    if not set(ids) <= set(roster):
        raise ValueError("deadline adapter cannot expose cases outside the selected corpus")
    bulk = Path(os.environ.get("PIPELINE_EVAL_BULK_ROOT", corpus.DEFAULT_BULK)).resolve()
    return [project(inputs[ident], bulk, cache) for ident in ids]


def unavailable(status, reason):
    return dict(
        status=status,
        reason=reason,
        boundary=policy.BOUNDARY,
        metrics={},
        arms={arm: dict(latlon=None, forced_latlon=None) for arm in ARMS},
    )


def solver_result(method, row, binding):
    result = row["result"]
    reason = result.get("reason") or ""
    if (
        binding is not None
        and method == COMPACT
        and result["status"] == "unavailable"
        and (reason == "AssertionError" or reason.startswith(SOLVER_EXCEPTIONS))
        and result["metrics"].get("candidate_s", 0) > 0
    ):
        return dict(result, status="failed")
    if method == SMOOTH and result["status"] in ("ok", "withheld"):
        receipt = row.get("input_binding") or {}
        if binding is None or any(receipt.get(key) != binding[key] for key in SHARED):
            return unavailable("failed", "smooth-clock worker returned a different input receipt")
    return result


def run(variant, case, base, seconds, affinity, output=None, *, now=monotonic):
    from ..__main__ import DEADLINE_VARIANTS, _input_receipt, implementation_digest, run_one

    total = DEADLINE_VARIANTS[variant]
    started = now()
    binding = case.get("binding")
    attempts = []

    def launch(method, source, allowance):
        limit = min(allowance, started + seconds - now())
        if limit <= 0:
            return policy.deadline_result()
        if method == SMOOTH:
            source = dict(source, timeout=limit)
        row = run_one(method, source, base, limit, affinity, output, supervised=True)
        result = solver_result(method, row, binding)
        attempts.append(
            dict(
                method=method,
                effective_budget_s=limit,
                raw_status=row["result"]["status"],
                raw_reason=row["result"].get("reason"),
                status=result["status"],
                worker_wall_s=row["worker_wall_s"],
                implementation_sha256=row.get("implementation_sha256"),
                input_sha256=row.get("input_sha256"),
            )
        )
        return policy.deadline_result() if now() > started + seconds else result

    if binding is None:
        result = unavailable("unavailable", case["unsupported"])
        state = dict(selected="none", calls=[], elapsed_s=now() - started)
    else:
        state = policy.route(
            lambda limit: launch(COMPACT, case["compact"], limit),
            lambda limit: launch(SMOOTH, case["smooth"], limit),
            total_s=total,
            now=now,
        )
        result = state.pop("result")
        names = {"compact": COMPACT, "smooth": SMOOTH}
        launched = {attempt["method"] for attempt in attempts}
        for call in state["calls"]:
            call["launched"] = names[call["method"]] in launched
        if names.get(state["selected"]) not in launched:
            state["selected"] = "none"
    metrics = dict(
        result["metrics"],
        deadline=dict(
            total_s=total,
            reserve_s=policy.RESERVE_S,
            supervisor_timeout_s=seconds,
            attempts=attempts,
            **state,
        ),
    )
    elapsed = now() - started
    return dict(
        id=case["id"],
        result=dict(result, metrics=metrics),
        call_s=elapsed,
        worker_wall_s=elapsed,
        implementation_sha256=implementation_digest(variant, Path(__file__)),
        **_input_receipt(binding),
    )


def watched_command(command, parent):
    return [sys.executable, "-B", "-m", __name__, str(parent), *command]


def watchdog(parent, command):
    import ctypes

    if os.getpgrp() != os.getpid():
        raise ValueError("deadline worker watchdog must own its isolated process group")

    def terminate(*_):
        os.killpg(os.getpgrp(), signal.SIGKILL)

    signal.signal(signal.SIGTERM, terminate)
    libc = ctypes.CDLL(None, use_errno=True)
    # Arm parent-death notification before checking for the startup race.
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    if os.getppid() != parent:
        terminate()
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(watchdog(int(sys.argv[1]), sys.argv[2:]))
