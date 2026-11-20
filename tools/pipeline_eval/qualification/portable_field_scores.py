"""Seal an independent DS26-0020 portable receiver comparison, then score it."""

import argparse
import gzip
import json
import math
from collections import Counter
from hashlib import sha256
from pathlib import Path

from .. import corpus, iq_service, original_receiver, whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import ARMS, POSITION_FAILURES, ROLES, arm_outcome, distance_km, distribution
from . import accelerated_command_results as accelerated
from . import capture_release, portable_field_parity
from . import capture_whole_results as capture
from .accelerated_command_archive import CASE
from .full_v5_check import BULK, _load_case, _sha

OUT = ROOT / "reports/2026_11_19_receiver_screening/native-receiver/portable-field"
HISTORICAL = accelerated.OUT
HISTORICAL_PREDICTION_SHA = "64307dc0bc1f361b6489d6676e2a8ac557a93fac3bcdf84ba2f45d8535ebd9da"
HISTORICAL_SCORE_SHA = "fbfea4e8cb75361c99befab18fb9aa028934429c8f7aff3e1b7e06facdae7b74"
SIGNATURE = "80c57275f989e685392fc3e47b8ceacf46b3a28031e1dbd2ec172483be5f55ff"
PORTABLE, ARCHIVE = "portable_field", "archived_compact"
POSITION = "positions.jsonl.gz"
PREDICTION_SEAL = "prediction-lock.json"
SIGNATURE_NAME = "SCORING-PROTOCOL.md"
LIVE_SEAL_NAME = "run-seal.json"
RUN_KEYS = ("source-lock.json", "summary.json")
read = whole_iq.read


def checked_files(directory, files, required=()):
    if not isinstance(files, dict) or not set(required) <= files.keys():
        raise ValueError(f"missing required evidence hashes under {directory}")
    for name, digest in files.items():
        p = Path(name)
        if (
            p.is_absolute()
            or ".." in p.parts
            or not (directory / p).resolve().is_relative_to(directory.resolve())
        ):
            raise ValueError(f"invalid sealed evidence path {name}")
        whole_iq.checked(directory / p, digest)


def historical(case):
    pred = read(whole_iq.checked(HISTORICAL / PREDICTION_SEAL, HISTORICAL_PREDICTION_SHA))
    score = read(whole_iq.checked(HISTORICAL / "score-lock.json", HISTORICAL_SCORE_SHA))
    checked_files(
        HISTORICAL, pred["files"], (POSITION, "archive-receipt.json", "compact-receipts.json")
    )
    checked_files(HISTORICAL, score["files"], ("original-v5-receipts.json",))
    pos = read(HISTORICAL / "compact-receipts.json")
    archive_receipt = read(HISTORICAL / "archive-receipt.json")
    archive = pos["archive"]
    native = whole_iq.checked(BULK / case["native"]["path"], case["native"]["sha256"])
    with gzip.open(HISTORICAL / POSITION, "rt") as stream:
        (archived,) = [
            row for row in map(json.loads, stream) if row["method"] == accelerated.ARCHIVE
        ]
    if (
        Path(archive_receipt["native_path"]) != native
        or archive_receipt["case_request_sha256"] != case["request"]["sha256"]
        or archive_receipt["position_sha256"] != archive["position_sha256"]
        or archive_receipt["service"] != archive["service"]
        or not iq_service.succeeded(archive["service"])
        or archived["native_sha256"] != case["native"]["sha256"]
        or archived["catalog_sha256"] != case["catalog"]["sha256"]
        or archived["tile"] != case["regions"][0]
    ):
        raise ValueError("archived compact position did not use the frozen independent control")
    return dict(
        archived=archived | {"method": ARCHIVE},
        native=read(native),
        archive_receipt=archive_receipt,
        archive_fit=archive,
        accelerated_fit=pos["secondary"],
        accelerated_raw=read(HISTORICAL / "secondary-raw-receipt.json"),
        accelerated_complete_command=read(HISTORICAL / "command-clock.json"),
        historical_v5_receipts=read(HISTORICAL / "original-v5-receipts.json"),
    )


def causal_authority(case):
    request = original_receiver.binding(case)
    history = request["causal_snapshots"]
    eligible = [
        (int(name.split("-")[0]), name)
        for name in history
        if int(name.split("-")[0]) < case["cutoff_utc_ns"]
    ]
    timestamp, name = max(eligible)
    digest = history[name].removeprefix("sha256:")
    if (timestamp, digest) != (case["catalog_timestamp_ns"], case["catalog"]["sha256"]):
        raise ValueError("latest strictly causal TLE differs from the frozen catalogue")
    whole_iq.checked(BULK / case["catalog"]["path"], digest)
    return request, dict(
        archive_snapshot_count=len(history),
        snapshot_count_before_cutoff=len(eligible),
        cutoff_utc_ns=case["cutoff_utc_ns"],
        selected_catalog_timestamp_ns=timestamp,
        selected_file=name,
        selected_sha256=digest,
        track_config_sha256=request["job"]["track_config"]["sha256"],
        original_request_sha256=case["request"]["sha256"],
    )


def verify_signed_visit(visit, index):
    acquisition = index["acquisition"]
    retune = json.loads(acquisition.get("retune_receipt") or "{}")
    expected = dict(
        sequence=index["sequence"],
        visit=acquisition["global_visit"],
        iq_sha256=index["iq_sha256"],
        sample_start=acquisition["sample_start"],
        sample_end=acquisition["sample_end"],
        input_bytes=index["payload_bytes"],
        generation=acquisition["generation"],
        delivery_clock=retune.get("host_delivery_clock"),
        clock_anchor=retune.get("utc_clock_bracket"),
    )
    if any(visit[key] != value for key, value in expected.items()):
        raise ValueError(f"visit {visit['visit']} shifted signed capture data")
    probes = visit["probes"]
    if visit["status"] == "processed" and [p["receiver_id"] for p in probes] == [0, 1]:
        if any(
            p["visit_index"] != visit["visit"] or p["valid_start_counter"] != visit["sample_start"]
            for p in probes
        ):
            raise ValueError("physical probe counters differ from their signed visit")
    elif visit["status"] != "invalid_capture" or probes:
        raise ValueError("signed visit lacks a pair of probes or an explicit capture exclusion")


def verify_signed_chunks(case, shards):
    manifests = []
    for locator in case["recording"]["segments"]:
        path = BULK / locator["path"]
        raw = original_receiver._read_prefix(path, 65537)
        if len(raw) > 65536 or sha256(raw).hexdigest() != locator["sha256"]:
            raise ValueError("signed segment manifest changed")
        manifest = json.loads(raw)
        manifests.append((path.parent, locator, manifest))
    indices = []
    for (segment, first), (chunk, visits) in sorted(shards.items()):
        root, locator, manifest = manifests[segment]
        (prior,) = [m for m in manifest["chunks"] if m["first_sequence"] == first]
        if (
            root != Path(chunk["path"])
            or chunk["manifest_digest"] != "sha256:" + locator["sha256"]
            or manifest["radio"]["serial"] != chunk["radio_id"]
            or chunk["compressed_bytes"] != prior["compressed_bytes"]
            or len(visits) != prior["window_count"]
        ):
            raise ValueError("closed raw chunk differs from the signed manifest")
        path = root / prior["index_relative_path"]
        data = original_receiver._read_prefix(path, prior["index_bytes"] + 1)
        if (
            len(data) != prior["index_bytes"]
            or "sha256:" + sha256(data).hexdigest() != prior["index_sha256"]
        ):
            raise ValueError("closed raw chunk index differs from its signed digest")
        for visit, index in zip(visits, map(json.loads, data.splitlines()), strict=True):
            verify_signed_visit(visit, index)
        indices.append(dict(segment=segment, first_sequence=first, sha256=prior["index_sha256"]))
    return indices


def visit_timings(visits):
    valid = [r for r in visits if r["status"] == "processed"]
    reports = {}
    for clock in ("cpu", "wall"):
        samples = [1000 * visit[f"detector_{clock}_s"] for visit in valid]
        if any(not math.isfinite(value) or value < 0 for value in samples):
            raise ValueError("valid visit has an invalid detector duration")
        reports[f"{clock}_ms"] = distribution(samples) | {
            "within_20_ms": sum(value <= 20 for value in samples),
            "sum_s": sum(samples) / 1000,
        }
    return reports


def raw_state(work, lock, summary, files):
    planned = {str(item[0]) for item in lock["workers"]}
    if "raw-exits.json" not in files:
        if iq_service.succeeded(summary.get("position_service") or {}):
            raise ValueError("successful position lacks a complete raw terminal")
        return dict(complete=False, completed=0, completed_chunks=0, valid=0, invalid=0), [], []
    required = {"launch.json", "raw-exits.json"} | {
        f"cpu-{cpu}.{suffix}" for cpu in planned for suffix in ("jsonl", "log")
    }
    if not required <= files.keys() or set(summary["raw_services"]) != planned:
        raise ValueError("terminal run does not seal all raw worker ledgers")
    configured = lock | {"workers": [(cpu, None, chunks) for cpu, _, chunks in lock["workers"]]}
    shards, workers, wall_s = capture.collect(work, configured)
    if "workers" in summary and workers != summary["workers"]:
        raise ValueError("runner summary differs from independently collected workers")
    for cpu, receipt in summary["raw_services"].items():
        key = f"raw-{cpu}"
        if (
            receipt["exit_code"] != workers[cpu]["exit_code"]
            or receipt["log_sha256"] != files.get(f"{key}/service.log")
            or receipt["binding"]["plan_sha256"] != files.get(f"{key}/plan.json")
            or read(work / key / "plan.json")
            != dict(
                stage="raw",
                cpus=[int(cpu)],
                limit_s=600,
                source_lock_sha256=files["source-lock.json"],
            )
        ):
            raise ValueError("raw worker clocks, service logs or affinity differ from their launch")
    indices = verify_signed_chunks(lock["case"], shards)
    visits = sorted(
        (row for _, rows in shards.values() for row in rows), key=lambda row: row["visit"]
    )
    valid = sum(r["status"] == "processed" for r in visits)
    scheduled = lock["case"]["recording"]["window_count"]
    worker_receipts = [r["terminal"] for r in workers.values() if r["terminal"] is not None]
    timing = visit_timings(visits)
    complete = len(visits) == scheduled and len(worker_receipts) == len(planned)
    return (
        dict(
            scheduled=scheduled,
            completed=len(visits),
            completed_chunks=len(shards),
            valid=valid,
            invalid=len(visits) - valid,
            compressed_bytes=sum(chunk["compressed_bytes"] for chunk, _ in shards.values()),
            detector_cpu_s=timing["cpu_ms"]["sum_s"],
            raw_worker_cpu_s=sum(
                r["end"]["cpu.stat.usage_usec"] - r["start"]["cpu.stat.usage_usec"]
                for r in worker_receipts
            )
            / 1e6
            if worker_receipts
            else None,
            raw_worker_cpu_coverage=len(worker_receipts),
            largest_worker_peak_bytes=max(
                (r["end"]["memory.peak"] for r in worker_receipts), default=None
            ),
            per_valid_visit=timing,
            wall_s=wall_s,
            raw_services=summary["raw_services"],
            workers=workers,
            authenticated_signed_indices=indices,
            complete=complete,
        ),
        visits,
        capture.summary_rows(shards),
    )


def position_record(work, lock, summary, files, request, native_hash, raw_complete):
    service = summary.get("position_service")
    if service and not raw_complete:
        raise ValueError("a live fit cannot follow an incomplete raw recording")
    if service:
        required = {
            "position/plan.json",
            "position/raw.json",
            "position/recording/request.json",
            "position/service.log",
        }
        if iq_service.succeeded(service):
            required |= {"position/start.json", "position/end.json", "position/position.json"}
        if not required <= files.keys():
            raise ValueError("compact service is missing sealed inputs or terminal evidence")
        plan = read(work / "position/plan.json")
        raw = read(work / "position/raw.json")
        position_request = read(work / "position/recording/request.json")
        job = position_request["job"]["native_input"]
        if (
            native_hash is None
            or Path(job["path"]) != work / "native.json"
            or job["sha256"] != native_hash
            or raw
            != dict(
                native_sha256=native_hash, request_sha256=files["position/recording/request.json"]
            )
            or plan["source_lock_sha256"] != files["source-lock.json"]
            or service["log_sha256"] != files["position/service.log"]
            or service["binding"]["plan_sha256"] != files["position/plan.json"]
        ):
            raise ValueError("compact service did not consume the fresh detector factors")
        whole_iq.verify_request(
            position_request, request, native_path=job["path"], native_sha256=native_hash
        )
    failure = summary["status"] if summary["status"] in POSITION_FAILURES else "failed"
    result, clock = accelerated.position_state(
        work, service, failure, files["source-lock.json"], lock["receiver"], lock["cpus"][0]
    )
    if iq_service.succeeded(service or {}) and result != summary.get("result"):
        raise ValueError("terminal live position differs from the sealed runner summary")
    return result, clock


def verify_live(work, case, request, reference):
    seal_path = work / LIVE_SEAL_NAME
    files = read(seal_path)["files"]
    checked_files(work, files, RUN_KEYS)
    lock, summary = (read(work / name) for name in RUN_KEYS)
    signed_plan = original_receiver.chunks(case)
    actual_plan = [tuple(chunk) for _, _, spans in lock["workers"] for chunk in spans]
    shared_capture = capture_release.read_capture(case)
    producer = capture_release.producer(case, shared_capture)
    shared_capture["case"] = {k: case[k] for k in ("id", "session_id", "run_id")}
    if (
        summary["id"] != CASE
        or summary["mode"] != "full"
        or lock["smoke"]
        or lock["id"] != CASE
        or lock["case"] != case
        or lock["recording"] != case["recording"]
        or sorted(actual_plan) != sorted(signed_plan)
        or [r[0] for r in lock["workers"]] != lock["cpus"]
        or lock["capture"] != shared_capture
        or lock["producer"] != str(producer.root)
        or lock["receiver"] != reference["archive_fit"]["plan"]["receiver"]
        or original_receiver.receiver_assets(Path(lock["receiver"])) != lock["receiver_files"]
        or lock["scoring_protocol_sha256"] != SIGNATURE
        or (lock["raw_limit_s"], lock["position_limit_s"]) != (600, 180)
    ):
        raise ValueError("live run differs from the frozen complete capture and compact fit")
    for name, digest in lock["sources"].items():
        whole_iq.checked(Path(name), digest)
    whole_iq.checked(Path(lock["python"]), lock["python_sha256"])
    for library in lock["libraries"].values():
        path = Path(library["path"])
        if files.get(path.relative_to(work).as_posix()) != library["sha256"]:
            raise ValueError("portable detector library differs from the sealed executable")
    raw, visits, samples = raw_state(work, lock, summary, files)
    native_hash = summary.get("native_sha256")
    native = None
    if native_hash is not None:
        if not raw["complete"] or files.get("native.json") != native_hash.removeprefix("sha256:"):
            raise ValueError("incomplete or unsealed native detector handoff")
        native = read(work / "native.json")
    result, fit = position_record(work, lock, summary, files, request, native_hash, raw["complete"])
    proof, differences, ambiguous = portable_field_parity.compare(
        native, visits, reference["native"]
    )
    resolved = bool(native_hash) and result["status"] in ("ok", "withheld")
    if proof["coverage"] == "complete_native" and native is None:
        raise ValueError("native parity could not be supported by a sealed handoff")
    elapsed = summary.get("command_wall_s")
    if elapsed is not None and (not math.isfinite(elapsed) or elapsed < (raw.get("wall_s") or 0)):
        raise ValueError("full command clock predates authenticated raw services")
    evidence = dict(
        status=result["status"],
        stage=summary["stage"],
        work=str(work),
        live_seal_sha256=_sha(seal_path),
        live_source_lock_sha256=files["source-lock.json"],
        cpus=lock["cpus"],
        sources=lock["sources"],
        build=lock["build"],
        raw=raw,
        fit=fit,
        command_wall_s=elapsed,
        command_setup_wall_s=summary.get("setup_wall_s"),
        native_sha256=native_hash,
        sealed_position=resolved,
    )
    return result, evidence, samples, visits, proof, differences, ambiguous


def collect_attempts(visits):
    flags = {
        1: "integer_gate",
        2: "fractional_gate",
        4: "fractional_complete",
        8: "fine_guard",
        16: "conditioned_tie",
        32: "glrt_bin_tie",
        64: "gate_guard",
        128: "equivalent_acquisition_tie",
    }
    rows, groups, anchor, tally = [], Counter(), Counter(), Counter()
    stages = Counter()
    for visit in visits:
        for group in visit["portable_groups"]:
            rows.append(dict(visit=visit["visit"], **group))
            groups[group["lane"]] += 1
            anchor[group["anchors"]] += 1
            scope = "published" if group["published"] else "replaced"
            tally[scope, "groups"] += 1
            for stage in ("coarse", "verify"):
                for clock in ("cpu", "wall"):
                    key = f"{stage}_{clock}_ns"
                    stages[key] += group[key]
            for candidate in group["candidates"]:
                bitmask = candidate["flags"]
                tally[scope, "attempted"] += 1
                for bit, name in flags.items():
                    tally[scope, name] += bool(bitmask & bit)
    return rows, dict(
        groups_by_lane=dict(groups),
        groups_by_anchor_budget=dict(anchor),
        attempt_counts={
            scope: {n: v for (s, n), v in tally.items() if s == scope}
            for scope in ("published", "replaced")
        },
        total_detector_stage_s={k.removesuffix("_ns") + "_s": v / 1e9 for k, v in stages.items()},
    )


def unavailable(reason, status="missing"):
    return dict(
        status=status,
        reason=reason,
        boundary="Signed original-schedule dual CI16 through portable C and compact position",
        metrics=dict(position_attempted=False),
        arms={arm: dict(latlon=None, forced_latlon=None) for arm in ARMS},
    )


def read_command_clock(path, runner_elapsed):
    clock = read(path)
    elapsed = clock["exit_observed_s"] - clock["start_s"]
    if (
        clock["clock"] != "CLOCK_BOOTTIME"
        or not clock["start_s"] <= clock["monitor_attach_s"] <= clock["exit_observed_s"]
        or elapsed != clock["process_elapsed_s"]
        or runner_elapsed is None
        or elapsed < runner_elapsed - 1 / clock["clock_ticks_s"]
    ):
        raise ValueError("independent command clock does not contain the runner interval")
    return clock


def seal(work, output, blocked=None, command_clock=None):
    from .armijo_finish_results import pack
    from .prefix_figures import csv_file

    whole_iq.checked(output / SIGNATURE_NAME, SIGNATURE)
    case = _load_case(CASE)
    inventory = accelerated.choose_inventory()
    request, causal = causal_authority(case)
    reference = historical(case)
    whole_iq.verify_request(
        reference["archive_fit"]["job"],
        request,
        native_path=reference["archive_receipt"]["native_path"],
        native_sha256=reference["archive_receipt"]["native_sha256"],
    )
    extra = {}
    if blocked is None:
        result, evidence, timings, visits, proof, differences, ambiguous = verify_live(
            work, case, request, reference
        )
        attempts, audit = collect_attempts(visits)
        evidence["attempt_ledger_summary"] = audit
        raw_seal = (work / LIVE_SEAL_NAME).read_bytes()
        if sha256(raw_seal).hexdigest() != evidence["live_seal_sha256"]:
            raise ValueError("live seal changed during independent verification")
        write(output / "live-run-seal.json", raw_seal)
        extra["live-run-seal.json"] = evidence["live_seal_sha256"]
        if command_clock is not None:
            evidence["command_clock"] = read_command_clock(
                command_clock, evidence["command_wall_s"]
            )
            save_json(output / "live-command-clock.json", evidence["command_clock"])
            extra["live-command-clock.json"] = _sha(output / "live-command-clock.json")
        diagnostic = output / "visit-931-coarse.json"
        if diagnostic.is_file():
            trace = read(diagnostic)
            if trace["portable_field_binary_sha256"] != evidence["build"]["binary"]["sha256"]:
                raise ValueError("coarse-grid diagnostic used a different binary from the live run")
            evidence["visit_931_coarse_diagnostic"] = trace
            extra[diagnostic.name] = _sha(diagnostic)
    else:
        if (work / LIVE_SEAL_NAME).exists():
            raise ValueError("a sealed live run must be verified before publishing coverage")
        result = unavailable(blocked)
        evidence = dict(
            status="missing",
            work=str(work),
            raw=dict(completed=0, completed_chunks=0, complete=False),
        )
        timings, attempts, differences, ambiguous = [], [], [], []
        proof = dict(
            coverage="unavailable", compared_visits=0, archived_total_visits=inventory["scheduled"]
        )
    binding = {
        k: v
        for k, v in reference["archived"].items()
        if k not in ("method", "result", "native_sha256")
    }
    predictions = [
        binding | dict(method=PORTABLE, native_sha256=evidence.get("native_sha256"), result=result),
        reference["archived"],
    ]
    compare = accelerated.compare_positions(
        [predictions[0], reference["archived"] | {"method": accelerated.ARCHIVE}]
    )
    clocks = reference["native"]["delivery_clocks"]
    archived_clock_s = (clocks[-1]["monotonic_ns"] - clocks[0]["monotonic_ns"]) / 1e9
    evidence.update(
        inventory=inventory,
        causal_authority=causal,
        recorded_delivery_span_s=archived_clock_s,
        archived_compact=reference["archive_fit"],
        accelerated_compact=reference["accelerated_fit"],
        accelerated_raw=reference["accelerated_raw"],
        accelerated_command=reference["accelerated_complete_command"],
        archive_position_comparison=compare[PORTABLE],
    )
    save_json(output / "field-evidence.json", evidence)
    save_json(output / "native-parity.json", proof)
    files = extra | {
        POSITION: pack(output, POSITION, predictions),
        "native-differences.jsonl.gz": pack(output, "native-differences.jsonl.gz", differences),
        "equivalent-peaks.jsonl.gz": pack(output, "equivalent-peaks.jsonl.gz", ambiguous),
        "portable-attempts.jsonl.gz": pack(output, "portable-attempts.jsonl.gz", attempts),
    }
    if timings:
        csv_file(output / "raw-visits.csv", timings)
        files["raw-visits.csv"] = _sha(output / "raw-visits.csv")
    files.update(
        {
            name: _sha(output / name)
            for name in (SIGNATURE_NAME, "field-evidence.json", "native-parity.json")
        }
    )
    save_json(
        output / PREDICTION_SEAL,
        dict(
            cases=[CASE],
            files=files,
            historical_prediction_sha256=HISTORICAL_PREDICTION_SHA,
            live_run_sha256=evidence.get("live_seal_sha256"),
            scoring_code={
                p.name: _sha(p) for p in (Path(__file__), Path(portable_field_parity.__file__))
            },
        ),
    )
    return evidence


def measured_scores(predictions, truth):
    rows = []
    for prediction in predictions:
        result = prediction["result"]
        for arm in ARMS:
            endpoint = result["arms"][arm]
            status, reason = arm_outcome(result, endpoint)
            rows.append(
                dict(
                    id=CASE,
                    method=prediction["method"],
                    arm=arm,
                    status=status,
                    reason=reason,
                    error_km=distance_km(endpoint["latlon"], truth),
                    forced_error_km=distance_km(endpoint.get("forced_latlon"), truth),
                    rf_rms_hz=endpoint.get("rf_rms_hz"),
                    frequency_score=result["metrics"].get(arm + "_frequency_score"),
                )
            )
    return rows


def subtract(a, b):
    return None if a is None or b is None else a - b


def accuracy(rows):
    indexed = {(r["method"], r["arm"]): r for r in rows}
    comparisons, ablation = {}, {}
    for method in (*ROLES, ARCHIVE):
        arms = comparisons[method] = {}
        for arm in ARMS:
            live, control = (indexed[key, arm]["error_km"] for key in (PORTABLE, method))
            multiplier = live / control if live is not None and control else None
            arms[arm] = dict(
                degradation_percent=None if multiplier is None else 100 * (multiplier - 1),
                within_5_percent=None if multiplier is None else multiplier <= 1.05,
                within_10_percent=None if multiplier is None else multiplier <= 1.10,
            )
    for method in (PORTABLE, ARCHIVE, *ROLES):
        c0, fitted = (indexed[method, arm] for arm in ARMS)
        ablation[method] = {
            field: subtract(fitted[field], c0[field])
            for field in ("error_km", "rf_rms_hz", "frequency_score")
        }
    primary = {
        key: [comparisons["baseline"][arm][key] for arm in ARMS]
        for key in ("within_5_percent", "within_10_percent")
    }
    return dict(
        comparison_by_control=comparisons,
        primary={key: None if None in values else all(values) for key, values in primary.items()},
        fitted_c_minus_c0=ablation,
    )


def score(output):
    from . import portable_field_report
    from .prefix_figures import csv_file

    prediction_path = output / PREDICTION_SEAL
    lock = read(prediction_path)
    checked_files(
        output,
        lock["files"],
        (POSITION, SIGNATURE_NAME, "field-evidence.json", "native-parity.json"),
    )
    if lock["cases"] != [CASE] or lock["files"][SIGNATURE_NAME] != SIGNATURE:
        raise ValueError("prediction seal differs from the frozen scoring signature")
    with gzip.open(output / POSITION, "rt") as stream:
        predictions = list(map(json.loads, stream))
    if [r["method"] for r in predictions] != [PORTABLE, ARCHIVE]:
        raise ValueError(
            "sealed results must contain the live prediction and archived compact control"
        )
    ids, files = corpus._selection("ds26-all159")
    (reference,) = corpus._references([ident for ident in ids if ident == CASE], files)
    v5, receipts = accelerated.original_v5_scores(_load_case(CASE), reference)
    old_receipts = read(HISTORICAL / "original-v5-receipts.json")
    if receipts != old_receipts:
        raise ValueError("historical v5 executions changed from the predeclared reference")
    rows = [*measured_scores(predictions, reference["truth"]), *v5]
    quality = accuracy(rows)
    evidence = read(output / "field-evidence.json")
    proof = read(output / "native-parity.json")
    save_json(output / "original-v5-receipts.json", receipts)
    csv_file(output / "scores.csv", rows)
    save_json(output / "scores.json", dict(rows=rows, accuracy=quality))
    output_files = portable_field_report.write_report(
        output, evidence, proof, rows, quality, receipts
    )
    score_files = (
        PREDICTION_SEAL,
        "original-v5-receipts.json",
        "scores.csv",
        "scores.json",
        *output_files,
    )
    save_json(
        output / "score-lock.json",
        dict(
            cases=[CASE],
            files=lock["files"] | {p: _sha(output / p) for p in score_files},
            frozen_scoring_sources={
                name: files[name] for name in ("inputs.jsonl", "scores.csv", "targets.jsonl")
            },
            scoring_code=lock["scoring_code"]
            | {
                Path(portable_field_report.__file__).name: _sha(
                    Path(portable_field_report.__file__)
                )
            },
        ),
    )
    portable_field_report.render_paired(output)
    return quality


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    seal_args = sub.add_parser("seal")
    seal_args.add_argument("work", type=local_output)
    seal_args.add_argument("--blocked", help="terminal failure when no live run seal exists")
    seal_args.add_argument("--command-clock", type=Path)
    seal_args.add_argument("--out", type=local_output, default=OUT)
    score_args = sub.add_parser("score")
    score_args.add_argument("--out", type=local_output, default=OUT)
    args = parser.parse_args()
    if args.operation == "seal":
        result = seal(args.work, args.out, args.blocked, args.command_clock)
        print(result["status"], result["raw"]["completed"])
    else:
        print(json.dumps(score(args.out), sort_keys=True))


if __name__ == "__main__":
    main()
