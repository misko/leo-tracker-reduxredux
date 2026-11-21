"""Replay matched measurement, coverage and orbit-support controls for compact v5."""

import argparse
import math
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ..variants import v5_lean, v5_orbit_domain, v5_secant_fit
from . import blind_compact_roster as panel
from . import recording_to_v5
from .blind_compact_score import strongest
from .full_v5_check import _sha
from .reverse_glrt_report import read
from .timing_first_position import full_identity

OUT = panel.OUT.parent / "2026_11_20_compact_position_diagnosis"
WORK = panel.WORK.parent / "gauss-compact-position-diagnosis-20261120"
TRACE_CASES = {"DS26-0197", "DS29-0074", "DS26-0221", "DS29-0385", "DS26-0259"}
FAST = ("checked", "cancellation")
HZ = "fractional_tracking_cfo_hz"


def receipt(case, method):
    path = panel.WORK / "runs" / case["id"] / method / "outcome.json"
    lock = read(panel.OUT / "prediction-lock.json")
    entry = next(r for r in lock["predictions"] if (r["case"], r["method"]) == (case["id"], method))
    if _sha(path) != entry["receipt_sha256"]:
        raise ValueError("the original experiment receipt changed")
    r = read(path)
    root = Path(r["prediction_path"]).parent
    for filename, key in (
        ("native.json", "native_sha256"),
        ("binding.json", "binding_sha256"),
        ("prediction.json", "prediction_sha256"),
    ):
        if _sha(root / filename) != entry[key]:
            raise ValueError(f"the frozen {filename} changed")
    return r, root


def same(a, b):
    if a is None or b is None:
        return False
    dt = (
        a["integer_epoch_sample"]
        - b["integer_epoch_sample"]
        + a["fractional_epoch_offset_samples"]
        - b["fractional_epoch_offset_samples"]
    )
    return abs(math.remainder(dt, 13333.0)) <= 2.0 and abs(a[HZ] - b[HZ]) <= 1000.0


def ident(probe):
    return probe["visit_index"], probe["receiver_id"], probe["valid_start_counter"]


def transform(original, fast, mode):
    """Modify only the winning frequency, or only original-empty opportunities."""
    if mode not in ("original_frequency", "added_only"):
        raise ValueError(mode)
    base = fast if mode == "original_frequency" else original
    changed = 0
    for a, b in zip(original["source"]["probes"], fast["source"]["probes"], strict=True):
        if ident(a) != ident(b) or a["actual_rf_hz"] != b["actual_rf_hz"]:
            raise ValueError("recordings have different hardware support")
        x, y = strongest(a), strongest(b)
        if mode == "original_frequency" and same(x, y):
            y[HZ] = x[HZ]
            changed += 1
        elif mode == "added_only" and x is None and y is not None:
            a["candidates"] = [dict(y)]
            changed += 1
    return base, changed


def rebind(case, document, folder, method, mode):
    source = document["source"]
    signature = recording_to_v5.digest(
        [mode, method, source["raw_recording_authority_digest"], source["probes"]]
    )
    source["analysis_manifest_sha256"] = signature
    document["provenance"].update(scope=method + "-" + mode, run_id="diagnosis-" + signature[7:39])
    native = folder / "native.json"
    recording_to_v5.save(native, document)
    public = recording_to_v5.bind_request(case, native, folder / "basic.json")
    req = read(folder / "basic.json")
    req["job"]["identity"]["run_id"] = full_identity(case["id"], req)
    binding = folder / "binding.json"
    recording_to_v5.save(binding, req)
    public["request_path"] = str(binding)
    return public


def public_for(case, root, r):
    return dict(
        id=case["id"],
        panel=case["panel"],
        session_id=case["session_id"],
        regions=case["regions"],
        request_path=str(root / "binding.json"),
        native_path=str(root / "native.json"),
        native_sha256="sha256:" + r["native_sha256"],
    )


def save_outcome(case, method, mode, folder, result, inputs, changed=None):
    prediction = folder / "prediction.json"
    recording_to_v5.save(prediction, result)
    record = dict(
        case=case["id"],
        method=method,
        mode=mode,
        status=result["status"],
        reason=result.get("reason"),
        inputs=inputs,
        changed=changed,
        prediction_path=str(prediction),
        prediction_sha256=_sha(prediction),
        protocol_sha256=_sha(OUT / "PROTOCOL.md"),
    )
    recording_to_v5.save(folder / "outcome.json", record)
    print(case["id"], method, mode, result["status"], result.get("reason"), flush=True)
    return record


def prior_outcome(folder):
    path = folder / "outcome.json"
    if path.is_file():
        r = read(path)
        if r["prediction_sha256"] != _sha(Path(r["prediction_path"])) or r[
            "protocol_sha256"
        ] != _sha(OUT / "PROTOCOL.md"):
            raise ValueError("previous diagnosis changed")
        return r
    return None


def run_one(case, method, mode):
    import tempfile

    root = WORK / case["id"] / method / mode
    root.mkdir(parents=True, exist_ok=True)
    if (cached := prior_outcome(root)) is not None:
        return cached
    folder = Path(tempfile.mkdtemp(prefix="attempt-", dir=root))
    r, src = receipt(case, method)
    public = public_for(case, src, r)
    inputs = [r["native_sha256"]]
    changed = None
    if mode == "orbit_support":
        if r["reason"] != "ValueError: " + v5_orbit_domain.OUTSIDE:
            raise ValueError("the causal fallback requires the exact interpolation exception")
        result = v5_orbit_domain.run(public, folder / "solver")
    elif mode == "local_orbit_support":
        previous = prior_outcome(WORK / case["id"] / method / "local_frequency")
        if previous is None or previous["reason"] != "ValueError: " + v5_orbit_domain.OUTSIDE:
            raise ValueError("local replay requires the matching interpolation exception")
        prior = Path(previous["prediction_path"]).parent
        public.update(
            native_path=str(prior / "native.json"),
            request_path=str(prior / "binding.json"),
            native_sha256=read(prior / "binding.json")["job"]["native_input"]["sha256"],
        )
        inputs.extend(
            [previous["prediction_sha256"], public["native_sha256"], _sha(OUT / "COMBINATION.md")]
        )
        result = v5_orbit_domain.run(public, folder / "solver")
    elif mode == "history_support":
        from . import compact_history_replay

        if (
            r["reason"] != "AssertionError"
            or "previous_bank" not in (src / "solver/worker.log").read_text()
        ):
            raise ValueError("target replay did not fail in earlier orbit propagation")
        inputs.append(_sha(OUT / "HISTORY.md"))
        result = v5_lean.run_bound_worker(
            public,
            folder / "solver",
            Path(compact_history_replay.__file__),
            worker_args=(str(src / "solver/orbit_projector.so"),),
        )
    elif mode in ("trace", "previous_orbit_failure"):
        from . import compact_position_owner_trace as trace

        result = v5_lean.run_bound_worker(
            public,
            folder / "solver",
            Path(trace.__file__),
            worker_args=(str(src / "solver/orbit_projector.so"), mode),
        )
        base = read(src / "prediction.json")
        if result["status"] != base["status"] or result["arms"] != base["arms"]:
            raise ValueError(
                f"owner replay differs from the original compact endpoint: {result.get('reason')}"
            )
    else:
        if mode == "local_frequency":
            from .compact_position_local import update

            document, changed, measurement_hash = update(case, method, read(src / "native.json"))
            inputs.append(measurement_hash)
        else:
            old, src0 = receipt(case, "original")
            inputs.append(old["native_sha256"])
            document, changed = transform(
                read(src0 / "native.json"), read(src / "native.json"), mode
            )
        public = rebind(case, document, folder, method, mode)
        del document
        result = v5_secant_fit.run(public, folder / "solver", "secant")
    record = save_outcome(case, method, mode, folder, result, inputs, changed)
    recording_to_v5.save(root / "outcome.json", record)
    return record


def lane(job):
    row, stage = job
    os.sched_setaffinity(0, {row["cpu"]})
    case = row["case"]
    if stage == "controls":
        for method in FAST:
            r, _ = receipt(case, method)
            if r.get("reason") == "ValueError: " + v5_orbit_domain.OUTSIDE:
                run_one(case, method, "orbit_support")
        for method in FAST:
            run_one(case, method, "original_frequency")
        run_one(case, "checked", "added_only")
    elif stage == "trace":
        for method in panel.METHODS:
            run_one(case, method, stage)
    elif stage == "previous_orbit_failure":
        run_one(case, "original", stage)
    elif stage == "history_support":
        for method in panel.METHODS:
            run_one(case, method, stage)
    elif stage == "local_frequency":
        from .compact_position_local import measure

        measure(case)
        for method in FAST:
            run_one(case, method, stage)
    elif stage == "local_orbit_support":
        for method in FAST:
            baseline = prior_outcome(WORK / case["id"] / method / "local_frequency")
            if baseline is None:
                raise ValueError("local frequency replay is pending")
            if baseline["reason"] == "ValueError: " + v5_orbit_domain.OUTSIDE:
                run_one(case, method, stage)
    else:
        raise ValueError(stage)


def run(stage):
    roster = read(panel.OUT / "roster.json")["cases"]
    if stage == "trace":
        roster = [r for r in roster if r["case"]["id"] in TRACE_CASES]
    if stage in ("previous_orbit_failure", "history_support"):
        roster = [r for r in roster if r["case"]["id"] == "DS26-0289"]
    WORK.mkdir(exist_ok=True, parents=True)
    with ProcessPoolExecutor(max_workers=len(roster)) as pool:
        list(pool.map(lane, [(r, stage) for r in roster]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=[
            "controls",
            "trace",
            "local_frequency",
            "previous_orbit_failure",
            "local_orbit_support",
            "history_support",
        ],
    )
    run(parser.parse_args().stage)
