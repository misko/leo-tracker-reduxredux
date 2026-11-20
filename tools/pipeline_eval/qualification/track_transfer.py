"""Benchmark the exact frozen track receiver across the archived transfer panels."""

import argparse
import gzip
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, THREAD_ENV, encoded, read_predictions, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from ..variants import rate_triplets, robust_em
from . import cold_scenes, fresh_scenes, identity_oracles, physical_transfer, robust_em_trials

OUTPUT = ROOT / "reports/2026_11_19_receiver_convergence/track-transfer"
PRIOR = ROOT / "reports/2026_11_19_short_receiver"
WORKER = Path(__file__).with_name("track_transfer_worker.py")
CPUS = (12, 13)
BEACON_RF_HZ = 11_325_000_000
METHOD = "robust_em"


def _read(path):
    return json.loads(path.read_bytes())


def _sha(raw):
    return sha256(raw).hexdigest()


def _hash(path):
    return _sha(path.read_bytes())


def availability(dataset, observation):
    """Describe the actual source observable without changing the numerical packet."""
    radio = {(row["receiver"], row["channel"], row["rf_hz"]) for row in observation["tracks"]}
    lanes = {2 * (receiver - 1) + int(channel > 4) for receiver, channel, _ in radio}
    if dataset == "starloc":
        if radio != {(1, 3, BEACON_RF_HZ)}:
            raise ValueError("StarLoc lane tags differ from the frozen common-frequency port")
        return dict(
            contract_eligible=False,
            radio_lanes=len(lanes),
            observable="shared StarLoc center-beacon CFO",
            reason="different carrier observable and only one independent lane",
        )
    if dataset != "synthetic_glrt":
        raise ValueError("unknown transfer source")
    return dict(
        contract_eligible=True,
        radio_lanes=len(lanes),
        observable="synthetic Qin GLRT folded CFO",
        reason=None,
    )


def linked_observation(capture):
    tracks = identity_oracles.tracklets(capture)
    return dict(
        anchor_utc_ns=capture.anchor_utc_ns,
        cutoff_utc_ns=capture.cutoff_utc_ns,
        catalog_timestamp_ns=capture.catalog_timestamp_ns,
        duration_s=capture.duration_s,
        tracks=[
            dict(
                receiver=row.receiver + 1,
                channel=row.channel,
                rf_hz=row.rf_hz,
                times=row.times.tolist(),
                values=row.cfo.tolist(),
            )
            for row in tracks
        ],
    )


def request(observation, catalogue, offer):
    if (
        set(observation) != physical_transfer.OBS_FIELDS
        or any(set(row) != physical_transfer.TRACK_FIELDS for row in observation["tracks"])
        or observation["catalog_timestamp_ns"] > observation["cutoff_utc_ns"]
    ):
        raise ValueError("unexpected observable fields or future catalogue")
    if set(offer) != {"id", "center", "width_km"}:
        raise ValueError("a request needs one bare offered tile")
    return encoded(dict(observation=observation, catalogue=catalogue, offer=offer))


def releases(output):
    original = robust_em_trials.source_hashes()
    if original != _read(PRIOR / "robust-em/source-lock.json"):
        raise ValueError("the exact robust_em release differs from its archive lock")
    files = (
        Path(__file__),
        WORKER,
        output / "PROTOCOL.md",
        Path(identity_oracles.__file__),
        Path(rate_triplets.__file__),
        Path(physical_transfer.__file__),
        Path(cold_scenes.__file__),
        Path(fresh_scenes.__file__),
    )
    return dict(
        method=METHOD,
        exact_release=original,
        experiment={str(path.relative_to(ROOT)): _hash(path) for path in files},
    )


def stage(fresh):
    archived_fresh = PRIOR / "fresh-scenes"
    if any(
        _hash(fresh / file) != _hash(archived_fresh / archive)
        for file, archive in (
            ("input-lock.json", "input-lock.json"),
            ("captures/input-lock.json", "capture-input-lock.json"),
            ("captures/public/manifest.json", "capture-manifest.json"),
            ("captures/public/offers.json", "offers.json"),
        )
    ):
        raise ValueError("fresh-scenes packet does not match the archived transfer panel")
    _, queries = fresh_scenes._check(fresh)
    public = fresh / "captures/public"
    capture_ids = _read(public / "manifest.json")["order"]
    if len(capture_ids) != 5:
        raise ValueError("need four synthetic sites and the locked shuffle")
    field, _, truth_hash = physical_transfer.stage()
    jobs = []
    for binding, raw in field:
        if binding["mode"] == "global":
            continue
        source = json.loads(raw)
        observation = source["observation"]
        offer = dict(id=binding["alias"], center=source["tile"], width_km=25.0)
        packet = request(observation, source["catalogue"], offer)
        mode = "supplied-correct" if binding["mode"] == "supplied-tile" else "omitted"
        jobs.append(
            (
                dict(
                    id=binding["alias"],
                    dataset="starloc",
                    group=binding["site_group"],
                    mode=mode,
                    target_key=binding["original_case"],
                    tile=offer,
                    observation_sha256=binding["observation_sha256"],
                    catalogue_sha256=binding["catalogue_sha256"],
                    input_sha256=_sha(packet),
                    **availability("starloc", observation),
                ),
                packet,
            )
        )
    for index, case in enumerate(capture_ids):
        started = perf_counter()
        capture = cold_scenes._capture(public, case)
        observation = linked_observation(capture)
        extraction_s = perf_counter() - started
        print("linked", case, len(observation["tracks"]), flush=True)
        case_queries = [query for query in queries if query["capture_id"] == case]
        if len(case_queries) != (1 if index == 4 else 2):
            raise ValueError("frozen synthetic offer roster mismatch")
        for query in case_queries:
            offer = dict(query["tile"], id=query["id"])
            packet = request(observation, capture.catalog.decode("ascii"), offer)
            jobs.append(
                (
                    dict(
                        id=query["id"],
                        dataset="synthetic_glrt",
                        group=case,
                        target_key=query["id"],
                        tile=offer,
                        link_wall_s=extraction_s,
                        native_sha256=capture.native_sha256,
                        observation_sha256=_sha(encoded(observation)),
                        catalogue_sha256=capture.catalog_sha256,
                        input_sha256=_sha(packet),
                        **availability("synthetic_glrt", observation),
                    ),
                    packet,
                )
            )
    if len(jobs) != 17 or len({binding["id"] for binding, _ in jobs}) != len(jobs):
        raise ValueError("the fixed transfer cohort must have 17 independent query IDs")
    return jobs, dict(
        starloc=truth_hash, synthetic_glrt=_read(fresh / "input-lock.json")["labels_sha256"]
    )


def _sandbox(cpu):
    command = robust_em_trials.sandbox(cpu)
    command[command.index(str(robust_em_trials.WORKER))] = str(WORKER)
    return command


def _run(cpu, binding, packet, implementation):
    start = perf_counter()
    try:
        proc = subprocess.run(
            _sandbox(cpu), input=packet, capture_output=True, timeout=45, check=True
        )
        out = json.loads(proc.stdout)
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        detail = (getattr(exc, "stderr", None) or b"").decode(errors="replace")[-1300:]
        status = "timed_out" if isinstance(exc, subprocess.TimeoutExpired) else "failed"
        out = dict(
            result=dict(
                status=status,
                reason=detail or str(exc),
                metrics={},
                boundary=robust_em.BOUNDARY,
                arms={arm: {"latlon": None, "forced_latlon": None} for arm in ARMS},
            )
        )
    validate_result(out["result"])
    elapsed = perf_counter() - start
    print(
        binding["dataset"],
        binding["group"],
        binding.get("mode", "sealed-offer"),
        out["result"]["status"],
        out["result"]["reason"],
        round(elapsed, 3),
        flush=True,
    )
    return dict(
        id=binding["id"],
        method=METHOD,
        worker_wall_s=elapsed,
        cpu=cpu,
        **out,
        implementation_sha256=implementation,
        input_sha256=binding["input_sha256"],
    )


def predict(output, fresh, scratch):
    if (output / "prediction-lock.json").exists():
        raise FileExistsError("the transfer predictions are already sealed")
    os.environ.update(THREAD_ENV)
    os.sched_setaffinity(0, CPUS)
    source = releases(output)
    save_json(output / "source-lock.json", source)
    jobs, truth = stage(fresh)
    plan = dict(truth_sha256=truth, queries=[b for b, _ in jobs], cpu=list(CPUS))
    save_json(output / "plan.json", plan)
    scratch.mkdir(mode=0o700)
    for binding, packet in jobs:
        write(scratch / f"{binding['id']}.json", packet)
    implementation = _sha(encoded(source["exact_release"]))
    with ThreadPoolExecutor(max_workers=len(CPUS)) as pool:
        tasks = [
            pool.submit(_run, CPUS[i % len(CPUS)], binding, packet, implementation)
            for i, (binding, packet) in enumerate(jobs)
        ]
        rows = [task.result() for task in tasks]
    path = output / "predictions.jsonl.gz"
    write(path, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))
    save_json(
        output / "prediction-lock.json",
        dict(
            predictions_sha256=_hash(path),
            source_lock_sha256=_hash(output / "source-lock.json"),
            plan_sha256=_hash(output / "plan.json"),
        ),
    )


def _score_row(binding, receipt, condition, target):
    result = receipt["result"]
    status = result["status"]
    arms = {}
    for key, arm in result["arms"].items():
        issued, forced = arm["latlon"], arm.get("forced_latlon")
        arms[key] = dict(
            status=status,
            issued=issued,
            forced=forced,
            issued_error_km=distance_km(issued, target),
            forced_error_km=distance_km(forced, target),
            rf_rms_hz=arm.get("rf_rms_hz"),
            c_hz_per_ghz=arm.get("c_hz_per_ghz"),
        )
    return dict(
        id=binding["id"],
        dataset=binding["dataset"],
        group=binding["group"],
        condition=condition,
        method=receipt["method"],
        status=status,
        reason=result["reason"],
        contract_eligible=binding["contract_eligible"],
        radio_lanes=binding["radio_lanes"],
        observable=binding["observable"],
        tile_error_km=distance_km(binding["tile"]["center"], target),
        false_published={
            arm: condition != "supplied-correct" and value["issued"] is not None
            for arm, value in arms.items()
        },
        worker_wall_s=receipt["worker_wall_s"],
        fit_wall_s=receipt.get("fit_wall_s"),
        link_wall_s=binding.get("link_wall_s"),
        metrics=result["metrics"],
        observable_check=receipt.get("observable_check"),
        arms=arms,
    )


def score(output, fresh):
    lock = _read(output / "prediction-lock.json")
    for field, path in (
        ("predictions", "predictions.jsonl.gz"),
        ("source_lock", "source-lock.json"),
        ("plan", "plan.json"),
    ):
        if lock[f"{field}_sha256"] != _hash(output / path):
            raise ValueError(f"the sealed {field} changed")
    plan = _read(output / "plan.json")
    raw_field = physical_transfer.STUDY / "field_private/truth.json"
    raw_synthetic = fresh / "captures/private/offer-labels.json"
    if _hash(raw_field) != plan["truth_sha256"]["starloc"] or (
        _hash(raw_synthetic) != plan["truth_sha256"]["synthetic_glrt"]
    ):
        raise ValueError("frozen coordinate labels changed")
    field = {row["id"]: row["latlon"] for row in _read(raw_field)["cases"]}
    synthetic = _read(raw_synthetic)
    rows = []
    predictions = read_predictions(output / "predictions.jsonl.gz")
    if set(predictions) != {binding["id"] for binding in plan["queries"]}:
        raise ValueError("predictions changed the frozen transfer cohort")
    for binding in plan["queries"]:
        receipt = predictions[binding["id"]]
        if binding["input_sha256"] != receipt["input_sha256"]:
            raise ValueError("prediction is not bound to the frozen transfer query")
        key = binding["target_key"]
        if binding["dataset"] == "starloc":
            condition, target = binding["mode"], field[key]
        else:
            info = synthetic[key]
            if info["capture_id"] != binding["group"]:
                raise ValueError("synthetic score would join a different capture")
            condition = {"present": "supplied-correct", "missing": "omitted", "shuffle": "shuffle"}[
                info["condition"]
            ]
            target = info["latlon"]
        rows.append(_score_row(binding, receipt, condition, target))
    save_json(
        output / "scores.json",
        dict(prediction_lock_sha256=_hash(output / "prediction-lock.json"), rows=rows),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("predict", "score"))
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--fresh", type=Path, required=True)
    parser.add_argument("--scratch", type=Path)
    args = parser.parse_args()
    if args.phase == "score":
        score(args.output, args.fresh)
    elif args.scratch is None:
        parser.error("--scratch is required for predict")
    else:
        predict(args.output, args.fresh, args.scratch)


if __name__ == "__main__":
    main()
