"""Read original v5 checkpoints and trace the same sealed bridge endpoints."""

import gzip
import hashlib
import json
import sys
from functools import wraps
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.qualification.bridge_cavity_eval import (
    REPORT,
    frozen_inputs,
    read,
    source_tokens,
)
from tools.pipeline_eval.variants import bridge_cavity

CASES = {"DS26-0066", "DS29-0082"}
ARMS = ("c0", "fitted_c")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected_initial(value):
    winner = next(
        row for row in value["choices"] if row["hypothesis"] == value["selected_hypothesis"]
    )
    rows = winner["node"]["seed"]["rows"]
    compatible = {
        r["component"] for r in winner["arms"]["c0"]["metrics"]["tracks"] if r["compatible"]
    }
    return dict(
        assigned={str(row["component"]): int(row["candidate_norad"]) for row in rows},
        gated=sorted(map(str, compatible)),
    )


def retained(value):
    return {
        a: dict(
            xy=np.asarray(value["arms"][a]["record"]["fit"]["parameters"]).tolist(),
            owners={
                str(row["component"]): dict(norad=int(row["norad"]), points=int(row["points"]))
                for row in value["arms"][a]["metrics"]["tracks"]
                if row["compatible"]
            },
        )
        for a in ARMS
    }


def pair(value):
    return {
        a: dict(
            xy=np.asarray(value[a]["endpoint_east_north_km"]).tolist(),
            rms_hz=float(value[a]["RMS_hz"]),
        )
        for a in ARMS
    }


def held(value):
    def summary(row):
        return {
            "norad": int(row["norad"]),
            "rms_hz": float(row["conditional_RMS_hz"]),
            "min_elevation_deg": float(row["minimum_elevation_deg"]),
        }

    return {
        str(f["original_norad"]): dict(
            ids_sha256=hashlib.sha256(
                "\n".join(sorted(f["held_observation_ids"])).encode()
            ).hexdigest(),
            points=f["held_points"],
            incumbent=summary(f["original"]),
            best=summary(f["best"]) if f["best"] is not None else None,
            predictive_gain=f["predictive_gain"],
        )
        for f in value["families"]
    }


def bridge_checkpoints(work, destination):
    from leo.analysis.localization_v3 import family_cavity, history_policy

    trace = {}

    def observe(original, handler):
        @wraps(original)
        def observed(*args, **kwargs):
            result = original(*args, **kwargs)
            handler(result, args)
            return result

        return observed

    def from_initialize(out, _):
        trace["initial"] = selected_initial(out[0])

    def from_history(out, args):
        trace["conservative"] = retained(args[1])
        trace["family"] = pair(out["policy_arms"])

    def from_cavity(out, args):
        trace["signed"] = pair(args[0]["arms"])
        trace["held"] = held(out)

    request = read(work / "request.json")
    request["job"]["output_root"] = str(destination.resolve())
    replay_request = destination / "request.json"
    replay_result = destination / "result.json"
    save_json(replay_request, request)
    with (
        patch.object(
            bridge_cavity, "initialize", observe(bridge_cavity.initialize, from_initialize)
        ),
        patch.object(
            history_policy, "history_policy", observe(history_policy.history_policy, from_history)
        ),
        patch.object(
            family_cavity,
            "nominate_families",
            observe(family_cavity.nominate_families, from_cavity),
        ),
    ):
        bridge_cavity.worker(replay_request, replay_result, work / "orbit_projector.so")
    result = read(replay_result)
    if result["status"] != "ok" or result["arms"] != read(work / "result.json")["arms"]:
        raise ValueError("diagnostic replay changed a sealed endpoint")
    trace["both_endpoints_and_rf_exact"] = True
    return trace


def original_checkpoints(ident):
    import evaluate_accuracy_repair as original

    binding = frozen_inputs()[ident]["request"]
    path = Path("/srv/bulk") / binding["path"]
    worker_path = path.with_name("worker-result.json")
    worker = read(worker_path)
    artifact = Path(worker["artifact"]["path"])
    expected = worker["artifact"]["sha256"].removeprefix("sha256:")
    receipt = read(path.with_name("validated-archive.json"))
    request = read(path)
    if (
        digest(path) != binding["sha256"]
        or digest(artifact) != expected
        or original.ev.digest(worker) != receipt["worker_sha256"]
        or original.ev.digest(request) != receipt["request_sha256"]
        or not receipt["validated"]
        or worker["artifact"] != receipt["artifact"]
    ):
        raise ValueError("original archive or request changed")
    codec = original.ev.owned_import("leo.storage.localization_v3_codec", request["source"])
    payload, _ = codec.unpack(artifact.read_bytes())
    if payload["request"] != request:
        raise ValueError("archive differs from original request")
    audit = payload["audit"]
    return dict(
        initial=selected_initial(audit["initial"]),
        conservative=retained(audit["recovery"]),
        family=pair(audit["history_policy"]["policy_arms"]),
        signed=pair(audit["signed_policy"]["arms"]),
        held=held(audit["cavity_nominations"]),
        original_archive_sha256=expected,
    )


def main(ident, results, destination):
    if ident not in CASES:
        raise ValueError("diagnostics are scoped to the two sealed regressions")
    lock = read(REPORT / "source-lock.json")
    if lock["source"] != source_tokens():
        raise ValueError("live bridge source differs from the sealed trial")
    with gzip.open(REPORT / "positions.jsonl.gz", "rt") as rows:
        sealed = next(row for row in map(json.loads, rows) if row["id"] == ident)
    work = Path(results) / ident / bridge_cavity.METHOD
    worker_sha256 = sealed["boundary_proof"]["worker_request_sha256"]
    if sealed["result"]["arms"] != read(work / "result.json")["arms"] or worker_sha256 != digest(
        work / "request.json"
    ):
        raise ValueError("replay request scratch folder differs from the sealed trial")
    output = Path(destination) / ident
    output.mkdir(parents=True, exist_ok=False)
    out = dict(
        id=ident,
        input_sha256=sealed["input_sha256"],
        trial_receipt_sha256=digest(REPORT / "receipt.json"),
        scientific_source_lock_sha256=digest(REPORT / "source-lock.json"),
        bridge=bridge_checkpoints(work, output),
        original=original_checkpoints(ident),
    )
    save_json(output / "trace.json", out)


if __name__ == "__main__":
    main(*sys.argv[1:])
