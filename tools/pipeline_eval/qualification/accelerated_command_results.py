"""Seal the public accelerated run before scoring its matched roof positions."""

import argparse
import csv
import gzip
import io
import json
import tarfile
from pathlib import Path

import numpy as np

from .. import corpus, iq_service, whole_iq
from ..__main__ import ROOT, encoded, save_json, write
from ..scoring import ARMS, ROLES, arm_outcome, distance_km, distribution, validate_result
from . import accelerated_command_parity as parity
from . import capture_whole_results as capture
from .accelerated_command_archive import CASE
from .armijo_finish_results import pack
from .full_v5_check import BULK, _sha
from .prefix_figures import csv_file
from .v5_postfit import ARCHIVE as V5_ARCHIVE

OUT = ROOT / "reports/2026_11_19_receiver_screening/original-schedule/accelerated-command"
MEASURED = "accelerated_command_measured"
ARCHIVE = "accelerated_command_archive"
SECONDARY = "accelerated_command_secondary"
BINDINGS = ("archived_native_sha256", "catalog_sha256", "original_request_sha256", "tile")
PLOT = "raw-and-fit.png"
MEMORY = 512 * 2**20


def read(path):
    return json.loads(path.read_bytes())


def choose_inventory():
    path = ROOT / "tools/pipeline_eval/frozen/inputs.jsonl"
    eligible = [
        (r["recording"]["window_count"], r["id"])
        for r in map(json.loads, path.read_bytes().splitlines())
        if r.get("native") and r.get("request") and r.get("run_id")
    ]
    count, name = min(eligible)
    if (name, count) != (CASE, 6764):
        raise ValueError("selected case differs from the frozen smallest eligible recording")
    return dict(inventory_sha256=_sha(path), eligible=len(eligible), id=name, scheduled=count)


def save_candidate_sources(checkout, locks):
    all_sources = {}
    for lock in locks:
        for name, digest in lock["sources"].items():
            if all_sources.setdefault(name, digest) != digest:
                raise ValueError("smoke and full services used different candidate source")
    path = checkout / "tools/pipeline_eval/original_receiver.py"
    if str(path) not in all_sources:
        raise ValueError("the actual worktree's public command must be source sealed")
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as target:
        for name, digest in sorted(all_sources.items()):
            local = whole_iq.checked(Path(name), digest)
            if local.is_relative_to(checkout):
                raw = local.read_bytes()
                tar = tarfile.TarInfo(local.relative_to(checkout).as_posix())
                tar.size = len(raw)
                target.addfile(tar, io.BytesIO(raw))
    write(OUT / "candidate-sources.tar.gz", gzip.compress(data.getvalue(), mtime=0))
    return all_sources


def position_state(directory, service, failure, source_sha, installed, expected_cpu):
    attempt = directory / "position"
    if service is None or not iq_service.succeeded(service):
        result = dict(
            status=failure,
            reason="public command or compact position service ended without a sealed position",
            boundary="Recorded native factors and independently capped compact receiver",
            metrics=dict(position_attempted=service is not None),
            arms={a: dict(latlon=None, forced_latlon=None) for a in ARMS},
        )
        validate_result(result)
        return result, {"service": service}
    path = attempt / "position.json"
    plan = read(attempt / "plan.json")
    raw = read(attempt / "raw.json")
    request = whole_iq.checked(attempt / "recording/request.json", raw["request_sha256"])
    whole_iq.checked(attempt / "service.log", service["log_sha256"])
    if (
        plan["source_lock_sha256"] != source_sha
        or plan["receiver"] != installed
        or plan["limit_s"] != 180
        or plan["cpus"] != [expected_cpu]
        or service["binding"]["plan_sha256"] != _sha(attempt / "plan.json")
    ):
        raise ValueError("position service left its matched launch")
    begin, end = (read(attempt / (n + ".json")) for n in ("start", "end"))
    if (
        any(
            d["memory.max"] != MEMORY
            or d["memory.swap.max"]
            or d["memory.swap.current"]
            or d["memory.events.oom_kill"]
            or d["cpus"] != [expected_cpu]
            for d in (begin, end)
        )
        or begin["cgroup"] != end["cgroup"]
        or begin["pid"] != end["pid"]
    ):
        raise ValueError("compact service left its independently capped boundary")
    result = read(path)
    validate_result(result)
    return result, dict(
        service=service,
        job=read(request),
        raw=raw,
        plan=plan,
        start=begin,
        end=end,
        position_sha256=_sha(path),
        worker_cpu_s=(end["cpu.stat.usage_usec"] - begin["cpu.stat.usage_usec"]) / 1e6,
        worker_wall_s=end["monotonic_s"] - begin["monotonic_s"],
        memory_peak_bytes=end["memory.peak"],
    )


def raw_evidence(directory, lock, summary):
    configured = lock | {"workers": [(cpu, None, chunks) for cpu, _, chunks in lock["workers"]]}
    runs = summary["raw_services"]
    try:
        shards, workers, elapsed = capture.collect(directory, configured)
        samples = capture.summary_rows(shards)
    except (ValueError, OSError) as error:
        if all(iq_service.succeeded(s) for s in runs.values()):
            raise
        return dict(error=str(error), raw_services=runs, complete=False), [], []
    if "workers" in summary and summary["workers"] != workers:
        raise ValueError("the public summary and independently collected raw shards disagree")
    valid = [r for r in samples if r["status"] == "processed"]
    clocks = [r["terminal"] for r in workers.values() if r["terminal"]]
    evidence = dict(
        scheduled=lock["case"]["recording"]["window_count"],
        completed=len(samples),
        completed_chunks=len(shards),
        valid=len(valid),
        invalid=len(samples) - len(valid),
        compressed_bytes=sum(r[0]["compressed_bytes"] for r in shards.values()),
        folded_calls=sum(r["folded_calls"] for r in samples),
        detector_cpu_s=sum(r["cpu_ms"] for r in valid) / 1000,
        raw_worker_cpu_s=sum(
            r["end"]["cpu.stat.usage_usec"] - r["start"]["cpu.stat.usage_usec"] for r in clocks
        )
        / 1e6,
        largest_worker_peak_bytes=max((r["end"]["memory.peak"] for r in clocks), default=None),
        wall_s=elapsed,
        workers=workers,
        raw_services=runs,
        per_valid_visit={
            k: distribution([r[k] for r in valid])
            | {"within_20_ms": sum(r[k] <= 20 for r in valid)}
            for k in ("wall_ms", "cpu_ms")
        },
        complete=len(samples) == lock["case"]["recording"]["window_count"]
        and all(w["exit_code"] == 0 for w in workers.values()),
    )
    closed = sorted((r for _, rows in shards.values() for r in rows), key=lambda r: r["visit"])
    return evidence, samples, closed


def partial_parity(visits, archived):
    """Retain comparisons on authenticated closed chunks without claiming full coverage."""
    selected = {r["visit"] for r in visits}
    first = [p for r in visits for p in r["probes"]]
    second = [p for p in archived["source"]["probes"] if p["visit_index"] in selected]
    proof, fields = parity.compare(
        {"source": {"probes": first}, "provenance": {}},
        {"source": {"probes": second}, "provenance": {}},
    )
    for k in (
        "schema_and_clock_fields_changed",
        "source_physical_fields_changed",
        "exclusion_and_authority_fields_changed",
    ):
        proof.pop(k)
    exclusions = {r["visit"] for r in archived["provenance"]["excluded_windows"]}
    proof.update(
        coverage="closed_chunks_only",
        compared_visits=len(selected),
        archived_total_visits=len(archived["delivery_clocks"]),
        delivery_clock_mismatches=[
            r["visit"]
            for r in visits
            if r["delivery_clock"] != archived["delivery_clocks"][r["visit"]]
        ],
        visit_validity_changes=[
            r["visit"]
            for r in visits
            if (r["status"] == "invalid_capture") != (r["visit"] in exclusions)
        ],
        first_clock_anchor_matches=visits[0]["clock_anchor"] == archived["clock_anchor"]
        if visits and visits[0]["visit"] == 0
        else None,
    )
    return proof, fields


def seal(work, checkout, command_clock, secondary=None):
    dirs = {n: work / n for n in ("smoke", "full", "archive")}
    if secondary is not None:
        dirs["secondary"] = secondary
    smoke, full, arc = (dirs[n] for n in ("smoke", "full", "archive"))
    locks = {name: read(d / "source-lock.json") for name, d in dirs.items()}
    smoke_lock, lock, archive_lock = (locks[n] for n in ("smoke", "full", "archive"))
    receipt = read(arc / "archive-receipt.json")
    summaries = {name: read(d / "summary.json") for name, d in dirs.items() if name != "archive"}
    full_summary = summaries["full"]
    if (
        receipt["source_lock_sha256"] != _sha(arc / "source-lock.json")
        or archive_lock != smoke_lock
        or not smoke_lock["smoke"]
        or lock["smoke"]
        or any(
            lock[k] != smoke_lock[k]
            for k in ("id", "case", "capture", "receiver", "receiver_files")
        )
        or lock["id"] != CASE
        or lock["coarse_search"]["fft_samples"] != 256
        or lock["coarse_search"]["planner"] != "stored-measure"
        or lock["peak_selector"]["backend"] != "row-wise"
        or lock["fine_search"]["frame_lanes"] != 4
        or lock["fine_search"]["backend"] != "batched"
        or len(lock["cpus"]) != 8
        or lock["raw_limit_s"] != 600
        or lock.get("interior_guard")
        or lock.get("fractional_stop")
    ):
        raise ValueError("unexpected source closure or accelerated runtime options")
    if secondary is not None:
        retry = locks["secondary"]
        fields = (
            "id",
            "case",
            "capture",
            "receiver",
            "receiver_files",
            "coarse_search",
            "peak_selector",
            "raw_limit_s",
            "position_limit_s",
            "smoke",
        )
        if (
            full_summary["status"] not in ("failed", "timed_out")
            or retry["cpus"] != list(range(8))
            or retry.get("interior_guard")
            or retry.get("fractional_stop")
            or any(retry[k] != lock[k] for k in fields)
            or any(
                retry["fine_search"][k] != lock["fine_search"][k]
                for k in ("backend", "frame_lanes", "qualification_sha256")
            )
            or retry["fine_search"]["library"]["sha256"] != lock["fine_search"]["library"]["sha256"]
        ):
            raise ValueError("secondary is only a matched normal replay after a terminal failure")
    source = save_candidate_sources(checkout, locks.values())
    case = lock["case"]
    binding = dict(
        id=CASE,
        recording=CASE,
        group="DS26",
        condition="present",
        tile=case["regions"][0],
        archived_native_sha256=case["native"]["sha256"],
        catalog_sha256=case["catalog"]["sha256"],
        original_request_sha256=case["request"]["sha256"],
    )
    original_bytes = whole_iq.checked(Path(receipt["native_path"]), receipt["native_sha256"])
    if _sha(original_bytes) != binding["archived_native_sha256"]:
        raise ValueError("archived fit did not use original detector factors")
    original_request = read(
        whole_iq.checked(
            BULK / case["request"]["path"],
            binding["original_request_sha256"],
        )
    )
    result, records = [], {}
    runs = [
        (
            "full",
            MEASURED,
            full_summary.get("position_service"),
            full_summary["status"],
            lock["cpus"][0],
        ),
        ("archive", ARCHIVE, receipt["service"], "failed", receipt["cpu"]),
    ]
    if secondary is not None:
        summary = summaries["secondary"]
        runs.append(
            (
                "secondary",
                SECONDARY,
                summary.get("position_service"),
                summary["status"],
                locks["secondary"]["cpus"][0],
            )
        )
    for name, method, service, failure, cpu in runs:
        if failure not in ("failed", "timed_out", "missing"):
            failure = "failed"
        outcome, terminal = position_state(
            dirs[name],
            service,
            failure,
            _sha(dirs[name] / "source-lock.json"),
            lock["receiver"],
            cpu,
        )
        native_sha = None
        if "job" in terminal:
            native = terminal["job"]["job"]["native_input"]
            whole_iq.checked(Path(native["path"]), native["sha256"])
            whole_iq.verify_request(
                terminal["job"],
                original_request,
                native_path=native["path"],
                native_sha256=native["sha256"],
            )
            native_sha = native["sha256"].removeprefix("sha256:")
            if terminal["raw"]["native_sha256"] != native["sha256"]:
                raise ValueError("compact service raw handoff and request used different native")
        elif name == "archive":
            native_sha = binding["archived_native_sha256"]
        result.append(binding | dict(method=method, native_sha256=native_sha, result=outcome))
        records[name] = terminal
    if records["archive"].get("position_sha256") != receipt["position_sha256"]:
        raise ValueError("archived compact output changed after its independent seal")
    archived = read(original_bytes)
    raw_fields = [
        p
        for name in ("full", "secondary")
        if name in dirs
        for p in seal_raw(dirs[name], name, locks[name], summaries[name], records[name], archived)
    ]
    save_json(OUT / "compact-receipts.json", records)
    save_json(OUT / "compact-parity.json", compare_positions(result))
    save_json(OUT / "archive-receipt.json", receipt)
    save_json(OUT / "public-summaries.json", summaries)
    if command_clock is not None:
        save_json(OUT / "command-clock.json", read(command_clock))
    save_json(
        OUT / "source-lock.json",
        dict(
            protocol_sha256=_sha(OUT / "PROTOCOL.md"),
            selected=choose_inventory(),
            command_checkout=str(checkout),
            candidate_sources=source,
            runtime_sources={n: read(d / "source-lock.json") for n, d in dirs.items()},
            runtime_source_locks={n: _sha(d / "source-lock.json") for n, d in dirs.items()},
            evaluation_sources={
                str(p.relative_to(ROOT)): _sha(p)
                for p in (
                    Path(__file__),
                    Path(parity.__file__),
                    Path(__file__).with_name(
                        "accelerated_command_archive.py",
                    ),
                    Path(capture.__file__),
                )
            },
        ),
    )
    fields = [
        "compact-receipts.json",
        "compact-parity.json",
        "archive-receipt.json",
        "public-summaries.json",
        "source-lock.json",
        "candidate-sources.tar.gz",
        "PROTOCOL.md",
    ]
    fields.extend(raw_fields)
    fields += ["command-clock.json"] if command_clock is not None else []
    files = {n: _sha(OUT / n) for n in fields}
    files["positions.jsonl.gz"] = pack(OUT, "positions.jsonl.gz", result)
    save_json(OUT / "prediction-lock.json", dict(cases=[CASE], files=files))


def compare_positions(rows):
    archive = next(r["result"] for r in rows if r["method"] == ARCHIVE)
    output = {}
    for row in rows:
        if row["method"] == ARCHIVE:
            continue
        fresh = row["result"]
        if any(r["status"] not in ("ok", "withheld") for r in (fresh, archive)):
            output[row["method"]] = {"available": False, "status": fresh["status"]}
            continue
        keys = set(fresh["metrics"]) | set(archive["metrics"])
        output[row["method"]] = dict(
            available=True,
            state_equal=all(fresh.get(k) == archive.get(k) for k in ("status", "reason")),
            arms_equal=fresh["arms"] == archive["arms"],
            non_timing_metrics_changed=sorted(
                k
                for k in keys - {"stage_s"}
                if fresh["metrics"].get(k) != archive["metrics"].get(k)
            ),
            paired_endpoint_separation_km={
                a: distance_km(fresh["arms"][a]["latlon"], archive["arms"][a]["latlon"])
                for a in ARMS
            },
        )
    return output


def seal_raw(directory, kind, lock, summary, terminal, archived):
    raw, visits, closed = raw_evidence(directory, lock, summary)
    if raw["complete"] and (raw["completed_chunks"], raw["completed"]) != (106, 6764):
        raise ValueError("the measured recording did not follow the frozen chunk inventory")
    prefix = "secondary-" if kind == "secondary" else ""
    proof = None
    fresh_hash = summary.get("native_sha256")
    if fresh_hash is not None:
        actual = read(whole_iq.checked(directory / "native.json", fresh_hash))
        if terminal.get("raw", {}).get("native_sha256", fresh_hash) != fresh_hash:
            raise ValueError("the final worker did not consume the recorded native output")
        proof, mismatches = parity.compare(actual, archived)
        proof["coverage"] = "complete_native"
        proof["archived_analysis_manifest_sha256"] = archived["source"]["analysis_manifest_sha256"]
        proof["accelerated_analysis_manifest_sha256"] = actual["source"]["analysis_manifest_sha256"]
        proof["archived_exclusions"] = archived["provenance"]["excluded_windows"]
        proof["accelerated_exclusions"] = actual["provenance"]["excluded_windows"]
    elif closed:
        proof, mismatches = partial_parity(closed, archived)
    fields = [prefix + n for n in ("native-parity.json", "raw-receipt.json")]
    if proof is not None:
        n = prefix + "native-differences.jsonl.gz"
        pack(OUT, n, mismatches)
        fields.append(n)
    save_json(OUT / (prefix + "native-parity.json"), proof)
    save_json(OUT / (prefix + "raw-receipt.json"), raw)
    if visits:
        n = prefix + "raw-visits.csv"
        csv_file(OUT / n, visits)
        fields.append(n)
    return fields


def records():
    lock = read(OUT / "prediction-lock.json")
    for p, digest in lock["files"].items():
        whole_iq.checked(OUT / p, digest)
    with gzip.open(OUT / "positions.jsonl.gz", "rt") as stream:
        rows = list(map(json.loads, stream))
    expected = [MEASURED, ARCHIVE]
    if "secondary-raw-receipt.json" in lock["files"]:
        expected.append(SECONDARY)
    if [r["method"] for r in rows] != expected:
        raise ValueError("missing measured/archived paired position")
    return rows, lock


def original_v5_scores(item, reference):
    directory = V5_ARCHIVE / f"{item['id']}-r0"
    rows, receipts = [], {}
    baseline = directory / "baseline/experimental-request.json"
    base = read(whole_iq.checked(baseline, item["request"]["sha256"]))
    latest = max(
        (int(name.split("-")[0]), digest.removeprefix("sha256:"))
        for name, digest in base["causal_snapshots"].items()
        if int(name.split("-")[0]) < item["cutoff_utc_ns"]
    )
    if latest != (item["catalog_timestamp_ns"], item["catalog"]["sha256"]):
        raise ValueError("the archived original v5 catalogue differs from the frozen causal digest")
    for role in ROLES:
        path = directory / role / "experimental-request.json"
        request = read(path)
        entry = directory / f"{role}-execution.json"
        execution = read(entry)
        digest = "sha256:" + corpus._sha(encoded(request))
        job = request["job"]
        if (
            request["role"] != role
            or execution["role"] != role
            or execution["request_sha256"] != digest
            or request["source"]["sha256"] != base["source"]["sha256"]
            or request["causal_snapshots"] != base["causal_snapshots"]
            or job["identity"]["session_id"] != item["session_id"]
            or job["evaluation_reference"] is not None
            or job["native_input"]["sha256"] != f"sha256:{item['native']['sha256']}"
            or job["search_center"] != item["regions"][0]["center"]
        ):
            raise ValueError(f"original {role} did not consume the frozen comparison inputs")
        success = execution["status"] == "complete"
        if success:
            worker = execution["worker"]
            if worker["request_sha256"] != digest or set(worker["arms"]) != set(ARMS):
                raise ValueError(f"original {role} omitted a bound numerical arm")
        elif execution["status"] != "timed_out" or "worker" in execution:
            raise ValueError(f"unexpected original {role} terminal result")
        for arm in ARMS:
            frozen = reference["reference"][role][arm]
            endpoint = execution["worker"]["arms"][arm] if success else {}
            point, rms = endpoint.get("endpoint_latlon"), endpoint.get("residual_rms_hz")
            if (
                point != frozen["latlon"]
                or rms != frozen["rf_rms_hz"]
                or frozen["status"] != ("fix" if success else "timed_out")
            ):
                raise ValueError(f"original {role}/{arm} differs from the official frozen scores")
            rows.append(
                dict(
                    id=item["id"],
                    method=role,
                    arm=arm,
                    status="ok" if success else "timed_out",
                    reason=None if success else "archived service deadline",
                    error_km=distance_km(point, reference["truth"]),
                    forced_error_km=None,
                    rf_rms_hz=rms,
                    frequency_score=None,
                )
            )
        receipts[role] = dict(
            status=execution["status"],
            execution_sha256=_sha(entry),
            request_sha256=digest,
            request_file_sha256=_sha(path),
            timeout_s=execution["timeout_seconds"],
            wall_s=execution["process"]["wall_seconds"],
        )
    return rows, receipts


def score():
    rows, lock = records()
    panel = "ds26-all159"
    ids, frozen_files = corpus._selection(panel)
    refs = {r["id"]: r for r in corpus._references(ids, frozen_files)}
    ref = refs[CASE]
    truth = ref["truth"]
    item = corpus._index(corpus._read_frozen("inputs.jsonl", frozen_files))[CASE]
    v5, v5_receipts = original_v5_scores(item, ref)
    scored = []
    for row in rows:
        result = row["result"]
        for arm in ARMS:
            endpoint = result["arms"][arm]
            status, reason = arm_outcome(result, endpoint)
            scored.append(
                dict(
                    id=CASE,
                    method=row["method"],
                    arm=arm,
                    status=status,
                    reason=reason,
                    error_km=distance_km(endpoint["latlon"], truth),
                    forced_error_km=distance_km(endpoint.get("forced_latlon"), truth),
                    rf_rms_hz=endpoint.get("rf_rms_hz"),
                    frequency_score=result["metrics"].get(arm + "_frequency_score"),
                )
            )
    scored.extend(v5)
    csv_file(OUT / "scores.csv", scored)
    save_json(OUT / "scores.json", dict(rows=scored))
    save_json(OUT / "original-v5-receipts.json", v5_receipts)
    has_secondary = any(r["method"] == SECONDARY for r in rows)
    stage = stage_rows(scored, has_secondary, "command-clock.json" in lock["files"])
    csv_file(OUT / "stage.csv", stage)
    plot(stage)
    save_json(
        OUT / "stage-figure.json",
        dict(
            version=1,
            id="accelerated-command-raw-and-fit",
            title="Accelerated public replay on the complete DS26-0020 recording",
            sample="Recorded lower edge with two separately CPU-pinned raw schedules."
            if has_secondary
            else "Recorded lower edge with eight CPU-pinned detector workers.",
            boundary="Native detector clocks exclude IQ decode and the compact position service.",
            note="Compact service wall clocks cover separate runs on different assigned cores.",
            seal="score-lock.json",
            image=PLOT,
            csv="stage.csv",
        ),
    )
    files = lock["files"] | {
        p: _sha(OUT / p)
        for p in (
            "prediction-lock.json",
            "original-v5-receipts.json",
            "scores.csv",
            "scores.json",
            "stage.csv",
            "stage-figure.json",
            PLOT,
        )
    }
    save_json(
        OUT / "score-lock.json",
        dict(
            cases=lock["cases"],
            files=files,
            frozen_scoring_sources={
                name: frozen_files[name] for name in ("inputs.jsonl", "scores.csv", "targets.jsonl")
            },
            scoring_code_sha256=_sha(Path(__file__)),
        ),
    )
    options = [("one", "Primary", MEASURED), ("stock", "Archive fit", ARCHIVE)]
    if has_secondary:
        options.append(("all_visits", "Completion", SECONDARY))
    series = []
    for key, label, method in options:
        row = dict(
            key=key,
            label=label,
            value=method,
            file="positions.jsonl.gz",
            native_field="archived_native_sha256",
        )
        if key != "one":
            row["match"] = list(BINDINGS)
        series.append(row)
    chart = dict(
        id="accelerated-command-ds26-0020",
        method=MEASURED,
        scope="roof",
        title="Public accelerated detector and archived-factor compact fit",
        caption="Same causal catalogue and 25 km tile. Primary and v5 two-omitted timed out.",
        cases=[CASE],
        seal="score-lock.json",
        provenance=["prediction-lock.json"],
        series=series,
    )
    save_json(OUT / "figures.json", dict(version=2, charts=[chart]))


def stage_rows(scored, has_secondary, has_command_clock):
    raw = read(OUT / "raw-receipt.json")
    compact = read(OUT / "compact-receipts.json")
    rows = []

    def row(panel, series, value, unit, visit=None, arm=None):
        rows.append(dict(panel=panel, series=series, visit=visit, arm=arm, value=value, unit=unit))

    for prefix, title in (("", "Primary"), ("secondary-", "Completion")):
        if prefix and not has_secondary:
            continue
        path = OUT / (prefix + "raw-visits.csv")
        if not path.is_file():
            continue
        with path.open() as stream:
            visits = [r for r in csv.DictReader(stream) if r["status"] == "processed"]
        for field, label in (("cpu_ms", "CPU"), ("wall_ms", "wall")):
            for sample in visits:
                row("visit", f"{title} {label}", float(sample[field]), "ms", visit=sample["visit"])
    row("visit_reference", "20 ms", 20, "ms")
    row("elapsed", "Primary raw", raw.get("wall_s"), "s")
    row("elapsed", "Archived compact", compact_wall(compact["archive"]), "s")
    if has_secondary:
        sec = read(OUT / "secondary-raw-receipt.json")
        row("elapsed", "Completion raw", sec.get("wall_s"), "s")
        row("elapsed", "Completion compact", compact_wall(compact["secondary"]), "s")
        if has_command_clock:
            elapsed = read(OUT / "command-clock.json")["process_elapsed_s"]
            row("elapsed", "Full completion", elapsed, "s")
    elif "start" in compact["full"]:
        row("elapsed", "Primary compact", compact_wall(compact["full"]), "s")
    for name, label in ((MEASURED, "Primary"), (ARCHIVE, "Archived"), (SECONDARY, "Completion")):
        for result in scored:
            if result["method"] == name and result["rf_rms_hz"] is not None:
                row("fit", label, result["rf_rms_hz"], "Hz", arm=result["arm"])
    return rows


def plot(stage):
    import matplotlib.pyplot as plt

    fig, (a, b, c) = plt.subplots(1, 3, figsize=(13.8, 4.7), layout="constrained")
    for label in ("Primary CPU", "Primary wall", "Completion CPU", "Completion wall"):
        points = sorted(r["value"] for r in stage if r["panel"] == "visit" and r["series"] == label)
        if points:
            a.step(points, np.arange(1, len(points) + 1) / len(points), label=label)
    ref = next(r for r in stage if r["panel"] == "visit_reference")
    a.axvline(ref["value"], color="0.4", linestyle=":")
    a.annotate(
        ref["series"],
        xy=(ref["value"], 0.65),
        xytext=(6, 0),
        textcoords="offset points",
        color="0.35",
    )
    a.set(
        xscale="log",
        xlabel="Per valid visit (ms)",
        ylabel="Fraction at or below duration",
        ylim=(0, 1.035),
    )
    if len(a.lines) > 1:
        a.legend(frameon=False, loc="lower right")
    elapsed = [r for r in stage if r["panel"] == "elapsed"]
    b.barh([r["series"] for r in elapsed], [r["value"] or 0 for r in elapsed], color="#328177")
    b.invert_yaxis()
    b.set(xlabel="Absolute elapsed time (s)")
    for i, (label, marker) in enumerate((("Primary", "o"), ("Archived", "x"), ("Completion", "d"))):
        data = [r for r in stage if r["panel"] == "fit" and r["series"] == label]
        if data:
            c.scatter(
                [ARMS.index(r["arm"]) + (i - 1) * 0.08 for r in data],
                [r["value"] for r in data],
                marker=marker,
                label=label,
            )
    c.set(xticks=(0, 1), xticklabels=("c = 0", "Fitted c"), xlim=(-0.25, 1.25))
    c.set(ylabel="Compact fitted CFO RMS (Hz)")
    c.legend(frameon=False)
    fig.savefig(OUT / PLOT, dpi=155)
    plt.close(fig)


def compact_wall(receipt):
    return (receipt.get("service") or {}).get("service_wall_s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    build = sub.add_parser("seal")
    build.add_argument("work", type=Path)
    build.add_argument("checkout", type=Path)
    build.add_argument("--command-clock", type=Path)
    build.add_argument("--secondary", type=Path)
    sub.add_parser("score")
    args = parser.parse_args()
    if args.action == "seal":
        seal(args.work, args.checkout.resolve(), args.command_clock, args.secondary)
    else:
        score()
