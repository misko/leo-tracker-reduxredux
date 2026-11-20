"""Check complete streamed raw factors, graph and positions against ordinary IQ."""

import argparse
import gzip
import json
import subprocess
from hashlib import sha256
from pathlib import Path

from ..__main__ import encoded, local_output, read_predictions, references, save_json, write
from ..scoring import ARMS, ROLES, distance_km, validate_result
from . import raw_robust, recording_to_v5
from . import raw_stream_trial as trial
from .full_v5_check import BULK, REPO, _load_case, _sha
from .prefix_figures import csv_file


def factor_classes(path):
    complete = json.loads(path.read_bytes())
    probes = complete["source"]["probes"]
    groups = {key: [] for key in ("passing_candidates", "rejected_candidates", "empty_probes")}
    for probe in probes:
        binding = {k: v for k, v in probe.items() if k != "candidates"}
        if not probe["candidates"]:
            groups["empty_probes"].append(binding)
        for row in probe["candidates"]:
            name = (
                "passing_candidates"
                if row["passed_fractional_margin_gate"]
                else "rejected_candidates"
            )
            groups[name].append([binding, row])
    groups["excluded_windows"] = complete["provenance"]["excluded_windows"]
    return {
        key: dict(count=len(value), sha256=sha256(encoded(value)).hexdigest())
        for key, value in groups.items()
    }


def graph(case, fresh, ordinary, fresh_checksum, ordinary_checksum):
    packets = [
        raw_robust.build_tracks(case, path, checksum, trial.PINS[0])
        for path, checksum in ((fresh, fresh_checksum), (ordinary, ordinary_checksum))
    ]
    keys = (
        "graph_status",
        "tracks",
        "selected_glrt_observations",
        "graph_assigned_observations",
        "active_curvature_tracks",
        "clock_half_width_s",
    )
    binding = [
        dict(
            projection_sha256=sha256(encoded(row["projection"])).hexdigest(),
            authority=row["authority"],
            counts={k: row["metrics"][k] for k in keys},
        )
        for row in packets
    ]
    return dict(
        equal=binding[0] == binding[1],
        candidate=binding[0],
        ordinary=binding[1],
        standalone_tracker=[row["metrics"]["tracker"] for row in packets],
    )


def publish(output, work):
    locked = json.loads(trial.SEAL.read_bytes())
    if locked != json.loads(recording_to_v5.encoded(trial.source_lock())):
        raise ValueError("completed replay differs from its frozen source lock")
    pairs = read_predictions(trial.CONTROL / "positions.jsonl.gz")
    baseline = json.loads((trial.CONTROL / "stage-receipts.json").read_bytes())
    rows, controls, receipts, graphs = [], [], {}, {}
    for ident in trial.CASES:
        case = _load_case(ident)
        prior = pairs[ident]
        source = work / ident
        measured = json.loads((source / "position.json").read_bytes())
        stage = json.loads((source / "stage-receipt.json").read_bytes())
        archive = raw_robust.prior_directory(ident) / "native.json"
        checksum = prior["native_sha256"]
        local = source / "native.json"
        for row in (measured, prior):
            validate_result(row["result"])
            if (
                row["id"] != ident
                or row["catalog_sha256"] != case["catalog"]["sha256"]
                or row["tile"] != case["regions"][0]
            ):
                raise ValueError("numerical inputs, catalogue or tile changed")
        if (
            measured["source_lock_sha256"] != _sha(trial.SEAL)
            or checksum != _sha(archive)
            or measured["native_sha256"] != _sha(local)
        ):
            raise ValueError("complete IQ-derived factor file changed after binding")
        old_classes, new_classes = factor_classes(archive), factor_classes(local)
        stage["candidate_factor_classes"] = new_classes
        stage["ordinary_factor_classes"] = old_classes
        stage["ordinary_full_reference"] = baseline[ident]
        stage["exact_ordinary_native"] = measured["native_sha256"] == checksum
        stage["same_factor_classes"] = new_classes == old_classes
        stage["same_positions_and_conditional_rf"] = (
            measured["result"]["arms"] == prior["result"]["arms"]
        )
        receipts[ident] = stage
        graphs[ident] = graph(case, local, archive, measured["native_sha256"], checksum)
        rows.append(measured)
        controls.append(prior)
    files = {}
    for name, values in (("positions.jsonl.gz", rows), ("ordinary-positions.jsonl.gz", controls)):
        path = output / name
        write(path, gzip.compress(b"".join(encoded(row) + b"\n" for row in values), mtime=0))
        files[name] = _sha(path)
    for name, contents in (("stage-receipts.json", receipts), ("graph-receipts.json", graphs)):
        save_json(output / name, contents)
        files[name] = _sha(output / name)
    if (probe_path := output / "reader-probe.json").is_file():
        files[probe_path.name] = _sha(probe_path)
    save_json(
        output / "prediction-lock.json",
        dict(cases=trial.CASES, files=files, source_lock_sha256=_sha(trial.SEAL)),
    )


def probe(output):
    if json.loads(trial.SEAL.read_bytes()) != json.loads(
        recording_to_v5.encoded(trial.source_lock())
    ):
        raise ValueError("bounded probe requires the frozen pair")
    probe_module = "tools.pipeline_eval.qualification.raw_stream_probe"
    results = {}
    for ident in trial.CASES:
        case = _load_case(ident)
        capture = recording_to_v5.capture_release.read_capture(case)
        root = recording_to_v5.capture_release.producer(case, capture).root
        entries = [dict(s, path=str(BULK / s["path"])) for s in case["recording"]["segments"]]
        rows = {}
        for mode in ("stock", "bounded"):
            command = [
                "taskset",
                "-c",
                str(trial.PINS[0]),
                "sudo",
                "-n",
                "-u",
                "leo",
                "--",
                "env",
                f"PYTHONPATH={root}:{REPO}",
                *(f"{k}={v}" for k, v in recording_to_v5.SINGLE_THREAD.items()),
                str(recording_to_v5.ARCHIVE_PYTHON),
                "-B",
                "-m",
                probe_module,
                mode,
            ]
            reply = subprocess.run(
                command,
                input=encoded(entries),
                capture_output=True,
                cwd=REPO,
                check=True,
                timeout=20,
            )
            rows[mode] = json.loads(reply.stdout)
        first, second = (rows[key] for key in ("stock", "bounded"))
        if any(first[k] != second[k] for k in ("manifest_sha256", "chunk", "windows_seen")):
            raise ValueError("largest-chunk comparison did not use identical bytes")
        results[ident] = rows
    save_json(output / "reader-probe.json", results)


def score(output):
    lock = json.loads((output / "prediction-lock.json").read_bytes())
    if lock["source_lock_sha256"] != _sha(trial.SEAL) or any(
        _sha(output / name) != digest for name, digest in lock["files"].items()
    ):
        raise ValueError("replay predictions or receipts changed after their lock")
    accepted = read_predictions(output / "positions.jsonl.gz")
    ordinary = read_predictions(output / "ordinary-positions.jsonl.gz")
    refs = {r["id"]: r for r in references("smoke", None)[1]}
    scores = []
    for ident in trial.CASES:
        ref = refs[ident]
        for arm in ARMS:
            before, after = (d[ident]["result"]["arms"][arm] for d in (ordinary, accepted))
            scores.append(
                dict(
                    id=ident,
                    arm=arm,
                    streamed_error_km=distance_km(after["latlon"], ref["truth"]),
                    ordinary_error_km=distance_km(before["latlon"], ref["truth"]),
                    streamed_conditional_rms_hz=after.get("rf_rms_hz"),
                    ordinary_conditional_rms_hz=before.get("rf_rms_hz"),
                    endpoint_shift_km=distance_km(after["latlon"], before["latlon"]),
                    **{role + "_km": ref["reference"][role][arm].get("error_km") for role in ROLES},
                )
            )
    csv_file(output / "scores.csv", scores)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("publish", "probe", "score"))
    parser.add_argument("--out", type=local_output, default=trial.REPORT)
    parser.add_argument("--work", type=Path)
    opts = parser.parse_args()
    if opts.action == "publish":
        if opts.work is None:
            parser.error("sealed publication requires both complete work directories")
        publish(opts.out, opts.work)
    elif opts.action == "probe":
        probe(opts.out)
    else:
        score(opts.out)


if __name__ == "__main__":
    main()
