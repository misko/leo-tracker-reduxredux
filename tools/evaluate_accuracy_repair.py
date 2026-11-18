"""Stage bounded DS26/DS29 repair experiments without changing public contracts.

Planning never runs inference. Running admits a bounded number of whole
recordings and resumes completed workers. Every role runs preparation, both
calibration arms, all diagnostic PNGs and experimental evidence serialization.
Evaluation references enter only the coordinator after worker completion.
"""

import argparse
import copy
import fcntl
import json
import math
import os
import random
import shutil
import signal
import subprocess
import time
from collections import Counter
from contextlib import suppress
from functools import partial
from pathlib import Path

import evaluate_algo07 as ev
from evaluate_initial_discovery import assignments, host, write

MODEL = "accuracy-repair-experiment-v1"
ORIGINAL = Path("/srv/bulk/leo-dev/ds26-ds29-evaluation-20261113")
PYTHON = "/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python"
DEFAULT_ROLES = ("baseline", "selective-gap", "omitted-tracks")
ROLES = (*DEFAULT_ROLES, "omitted-track-one")
DIAGNOSTIC = (
    "DS26-0050",
    "DS26-0012",
    "DS26-0130",
    "DS26-0185",
    "DS26-0120",
    "DS29-0399",
    "DS29-0233",
    "DS29-0082",
    "DS29-0546",
    "DS29-0070",
    "DS29-0106",
    "DS29-0289",
    "DS29-0515",
)
DEVELOPMENT = (
    *DIAGNOSTIC,
    "DS26-0066",
    "DS26-0098",
    "DS26-0104",
    "DS29-0163",
    "DS26-0002",
    "DS26-0102",
    "DS26-0263",
    "DS29-0126",
    "DS26-0020",
)
CACHE = Path("/home/mouse9911/.cache/accuracy-repair-20261115")
DEFAULT_COHORTS = {
    "DS26": dict(snapshot="/srv/bulk/leo-dev/algo07v3-shortcuts-20261107", references=None),
    "DS29": dict(
        snapshot="/srv/bulk/leo-dev/ds29-20261113/snapshot",
        references="/srv/bulk/leo-dev/ds29-20261113/snapshot/evaluation-references.json",
    ),
}
POLICIES = {
    "baseline": "fast-v5-zero-recovery-control-v1",
    "selective-gap": "selective-timing-gap-prediction-experiment-v1",
    "omitted-tracks": "omitted_uncurved_calibrated_v1",
    "omitted-track-one": "omitted_uncurved_calibrated_one_experiment_v1",
}
ENVIRONMENT = dict(
    os.environ,
    PYTHONDONTWRITEBYTECODE="1",
    OPENBLAS_NUM_THREADS="1",
    OMP_NUM_THREADS="1",
    MKL_NUM_THREADS="1",
)


def bulk_output(path):
    path = ev.local_output(path)
    if not path.is_relative_to("/srv/bulk") and not path.is_relative_to(CACHE):
        raise ValueError(
            "Experiment outputs must be beneath /srv/bulk or the authorized bounded cache"
        )
    return path


def recording_selection(members, *, profile, seed, cases=None, groups=1):
    if profile == "diagnostic" and cases is None:
        raise ValueError("Diagnostic profile requires explicit cases")
    by_case = {m["dataset_label"]: m for m in members}
    diagnostic_groups = {m["recording_id"] for m in members if m["dataset_label"] in DIAGNOSTIC}
    development_groups = {m["recording_id"] for m in members if m["dataset_label"] in DEVELOPMENT}
    development = [m["dataset_label"] for m in members if m["recording_id"] in development_groups]
    selected = assignments(
        members,
        seed=seed,
        profile="quick" if profile == "holdout" else "full" if profile == "full" else "development",
        cases=cases,
        development=development,
        quick_groups=groups,
    )
    selected["diagnostic_cases"] = sorted(
        m["dataset_label"] for m in members if m["recording_id"] in diagnostic_groups
    )
    selected["development_cases"] = sorted(development)
    selected["untouched_cases"] = sorted(set(selected["cases"]) - set(development))
    selected["case_groups"] = {case: by_case[case]["recording_id"] for case in selected["cases"]}
    return selected


def prepare(args):
    output = bulk_output(args.output)
    source = ev.source_binding(args.source_root)
    cohorts = ev.read(args.cohorts) if args.cohorts else DEFAULT_COHORTS
    if set(cohorts) - {"DS26", "DS29"} or not cohorts:
        raise ValueError("Cohorts must contain DS26 and/or DS29")
    roles = args.roles.split(",")
    if len(roles) != len(set(roles)) or not set(roles) <= set(ROLES):
        raise ValueError("Unique experimental roles required")
    if "baseline" not in roles:
        roles.insert(0, "baseline")
    if (
        not 1 <= args.repeats <= 100
        or not math.isfinite(args.timeout)
        or not 1 <= args.timeout <= 2400
    ):
        raise ValueError("Repetitions must be 1..100 and timeout 1..2400 seconds")
    paths = [
        Path(__file__),
        Path(ev.__file__),
        Path(__file__).with_name("evaluate_initial_discovery.py"),
        Path(__file__).with_name("initial_discovery_archive.py"),
        args.native_manifest.resolve(),
    ]
    if args.cohorts:
        paths.append(args.cohorts.resolve())
    native = ev.read(args.native_manifest)
    paths += [Path(native[key]) for key in ("binary", "source", "wrapper")]
    paths.append(Path(native["provider"]["path"]))
    documents, schedule = {}, []
    requested = set(args.cases.split(",")) if args.cases else None
    found = set()
    for name, specification in cohorts.items():
        snapshot = Path(specification["snapshot"]).resolve()
        inventory = ev.read(snapshot / "inventory.json")
        template = ev.read(snapshot / "template-request.json")
        members = inventory["members"]
        if any(not m["dataset_label"].startswith(name + "-") for m in members):
            raise ValueError("Inventory belongs to another dataset")
        labels = {m["dataset_label"] for m in members}
        cases = sorted(requested & labels) if requested is not None else None
        if requested is not None and not cases:
            continue
        found.update(cases or [])
        selected = recording_selection(
            members,
            profile=args.profile,
            seed=args.seed + ":" + name,
            cases=",".join(cases) if cases is not None else None,
            groups=args.groups_per_dataset,
        )
        references = (
            Path(specification["references"]).resolve() if specification.get("references") else None
        )
        if name == "DS29" and references is None:
            raise ValueError("DS29 requires explicit evaluation-only references")
        reference_map = ev.read(references) if references else {}
        config = snapshot / "inputs/config.json"
        if ev.file_digest(config) != "sha256:" + inventory["config_sha256"].removeprefix("sha256:"):
            raise ValueError("Frozen configuration digest differs")
        paths += [
            snapshot / filename
            for filename in ("inventory.json", "template-request.json", "inputs/config.json")
        ]
        if references:
            paths.append(references)
        documents[name] = dict(
            snapshot=str(snapshot),
            members=members,
            selection=selected,
            config_sha256=ev.file_digest(config),
            template=template,
            references={
                case: reference_map.get(case, template.get("evaluation_reference"))
                for case in selected["cases"]
            },
        )
        for repetition in range(args.repeats):
            for case in selected["cases"]:
                order = list(roles)
                # Adjacent repetitions counterbalance first/last role positions exactly.
                random.Random(args.seed + ":" + case + ":" + str(repetition // 2)).shuffle(order)
                if repetition % 2:
                    order.reverse()
                schedule.append(
                    dict(
                        dataset=name,
                        case=case,
                        repetition=repetition,
                        group=selected["case_groups"][case],
                        order=order,
                        split="diagnostic"
                        if case in selected["diagnostic_cases"]
                        else "development"
                        if case in selected["development_cases"]
                        else "untouched",
                    )
                )
    if requested is not None and found != requested:
        raise ValueError("Explicit cases must be frozen cohort members")
    group_order = sorted({(row["dataset"], row["group"]) for row in schedule})
    random.Random(args.seed + ":schedule").shuffle(group_order)
    rank = {group: index for index, group in enumerate(group_order)}
    schedule.sort(
        key=lambda row: (rank[row["dataset"], row["group"]], row["repetition"], row["case"])
    )
    return dict(
        schema_version=1,
        model=MODEL,
        output=str(output),
        source=source,
        worker=str(Path(__file__).resolve()),
        python=PYTHON,
        native_manifest=native,
        native_manifest_path=str(args.native_manifest.resolve()),
        profile=args.profile,
        seed=args.seed,
        roles=roles,
        policies={role: POLICIES[role] for role in roles},
        timeout_seconds=args.timeout,
        repeats=args.repeats,
        cohorts=documents,
        schedule=schedule,
        bindings={str(path): ev.file_digest(path) for path in paths},
        reference_usage="coordinator evaluation only; absent from worker requests",
        accuracy="c0 and fitted_c reported separately; DS29 uses operator reference locations",
        timing_scope=("fresh complete experimental worker including preparation, inference, "
                      "PNGs and archive save"),
        execution_mode=("contended; paired wall time is descriptive, "
                        "not an isolated speed qualification"),
    )


def check_bindings(manifest):
    if manifest.get("model") != MODEL or manifest.get("schema_version") != 1:
        raise ValueError("Experimental manifest required")
    for name, expected in manifest["bindings"].items():
        if ev.file_digest(name) != expected:
            raise ValueError("Frozen input changed: " + name)
    if ev.source_binding(manifest["source"]["root"]) != manifest["source"]:
        raise ValueError("Frozen source tree changed")


def worker_request(manifest, assignment, role):
    cohort = manifest["cohorts"][assignment["dataset"]]
    (member,) = [m for m in cohort["members"] if m["dataset_label"] == assignment["case"]]
    if member["availability"] != "available":
        return None
    snapshot = Path(cohort["snapshot"])
    folder = (
        Path(manifest["output"])
        / (assignment["case"] + "-r" + str(assignment["repetition"]))
        / role
    )
    job = copy.deepcopy(cohort["template"])
    job.update(
        native_input=dict(
            path=str(snapshot / "inputs" / assignment["case"] / "native.json"),
            sha256=member["input_sha256"],
        ),
        track_config=dict(
            path=str(snapshot / "inputs/config.json"), sha256=cohort["config_sha256"]
        ),
        tle_root=str(snapshot / "inputs" / assignment["case"] / "tle"),
        output_root=str(folder),
        scan_identities=[member["session_id"]],
        title=member["recording_id"],
        evaluation_reference=None,
    )
    job["identity"] = dict(
        run_id="experiment-"
        + ev.digest(
            dict(
                case=assignment["case"],
                repetition=assignment["repetition"],
                role=role,
                source=manifest["source"]["sha256"],
                native=manifest["native_manifest"],
                input=member["input_sha256"],
            )
        )[7:47],
        session_id=member["session_id"],
        input_sha256=member["input_sha256"],
    )
    return dict(
        schema_version=1,
        model=MODEL,
        role=role,
        policy=manifest["policies"][role],
        source=manifest["source"],
        native_manifest=manifest["native_manifest"],
        causal_snapshots=member["causal_snapshots"],
        job=job,
    )


def check_scientific_inputs(request):
    job = request["job"]
    if job["evaluation_reference"] is not None:
        raise ValueError("Evaluation reference leaked into inference")
    for key in ("native_input", "track_config"):
        if ev.file_digest(job[key]["path"]) != job[key]["sha256"]:
            raise ValueError("Frozen scientific input changed: " + key)
    paths = list(Path(job["tle_root"]).rglob("*.tle"))
    by_name = {p.name: p for p in paths}
    if len(by_name) != len(paths) or set(by_name) != set(request["causal_snapshots"]):
        raise ValueError("Frozen causal TLE membership changed")
    for name, expected in request["causal_snapshots"].items():
        if ev.file_digest(by_name[name]) != "sha256:" + expected.removeprefix("sha256:"):
            raise ValueError("Frozen causal TLE changed: " + name)


def execution_ports(request, receipts, emit):
    from leo.analysis.localization_v4.backend import ProcessBound
    from leo.analysis.localization_v5.annotation_fallback import fit
    from leo.analysis.localization_v5.initial_control import initial_control
    from leo.application.localization_v3_engine import ExecutionPorts
    from leo.contracts import localization_v5 as contract
    from leo.operations import localization_v3_parallel as parallel
    from leo.operations.localization_v3_job import stage_deadline
    from leo.operations.localization_v5_controls import ControlCacheFactory
    from leo.operations.localization_v5_joint import JointScheduleFactory
    from leo.operations.localization_v5_training import ProcessTrainingFit

    backend = ProcessBound(request["native_manifest"], receipts / "native")
    training = ProcessTrainingFit(fit, receipts)
    controls = ControlCacheFactory(
        backend, contract.inclusion_control_policy("native-complete-controls-v1")
    )
    joint = JointScheduleFactory(
        backend, contract.joint_schedule_policy("defer-factorized-unless-retry-v1")
    )

    def stage(name, operation):
        try:
            value = operation()
        except Exception as error:
            emit(
                dict(
                    event="recovery_stage",
                    stage=name,
                    status="failed",
                    error=f"{type(error).__name__}: {error}",
                )
            )
            return False, None
        emit(dict(event="recovery_stage", stage=name, status="complete"))
        return True, value

    def gap(name, operation, cap):
        with stage_deadline(cap):
            value = operation()
        return True, value

    experimental = {}
    if request["role"] == "selective-gap":
        from leo.analysis.localization_v3.gap_prediction import screen_timing_targets

        experimental.update(
            gap_target_filter=screen_timing_targets,
            direct_gap_policy=contract.direct_gap_policy("direct-timing-gap-v1"),
        )
    elif request["role"] in ("omitted-tracks", "omitted-track-one"):
        from leo.analysis.localization_v3.omitted_track_proposals import rank_omitted_tracks

        experimental["recovery_target_selector"] = (
            partial(rank_omitted_tracks, max_proposals=1)
            if request["role"] == "omitted-track-one"
            else rank_omitted_tracks
        )
    ports = ExecutionPorts(
        stage,
        gap,
        lambda: True,
        lambda _: None,
        time.monotonic,
        map_initial_arms=parallel.map_initial_arms,
        map_initial_branches=parallel.map_initial_branches,
        map_predictive_folds=parallel.map_predictive_folds,
        map_family_arms=parallel.map_initial_arms,
        map_recovery_arms=parallel.map_initial_arms,
        map_conservative_arms=parallel.map_initial_arms,
        map_annotation_training=parallel.map_annotation_training,
        map_grid_batches=parallel.map_grid_batches,
        bound=backend,
        initial_control=initial_control,
        annotation_training_fit=training,
        inclusion_control_factory=controls,
        joint_schedule_factory=joint,
        recovery_target_limit=0,
        **experimental,
    )

    def provenance():
        return dict(
            native_backend=backend.provenance(),
            annotation_training_work=training.provenance(),
            inclusion_control_work=controls.provenance(),
            joint_schedule_work=joint.provenance(),
        )

    return ports, provenance


def execute_worker(path):
    request = ev.read(path)
    if (
        set(request)
        != {
            "schema_version",
            "model",
            "role",
            "policy",
            "source",
            "native_manifest",
            "causal_snapshots",
            "job",
        }
        or request["schema_version"] != 1
        or request["model"] != MODEL
        or request["role"] not in ROLES
        or request["policy"] != POLICIES[request["role"]]
    ):
        raise ValueError("Bound experimental worker request required")
    source = request["source"]
    ev.owned_import("leo.application.localization_v3_engine", source)
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.application.localization_v3_engine import run_native
    from leo.application.localization_v3_result import audit_evidence
    from leo.operations.localization_v3_job import read_bound, runtime_versions, validate_request
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.localization_v3_codec import pack, unpack

    job = validate_request(request["job"])
    if runtime_versions() != job["runtime"]:
        raise ValueError("Numerical runtime differs from frozen request")
    if ev.source_binding(source["root"]) != source:
        raise ValueError("Worker source binding changed")
    check_scientific_inputs(request)
    destination = bulk_output(job["output_root"])
    def emit(value):
        print(json.dumps(value, sort_keys=True, allow_nan=False), flush=True)

    ports, provenance = execution_ports(request, destination / "receipts", emit)
    document = read_bound(job["native_input"])
    if document["source"]["session_id"] != job["identity"]["session_id"]:
        raise ValueError("Native input belongs to another session")
    result = run_native(
        document,
        TleArchiveReader(Path(job["tle_root"])),
        TrackConfig(**read_bound(job["track_config"])["config"]),
        SearchRegion(tuple(job["search_center"])),
        identities=job["scan_identities"],
        execution=ports,
        screen_latitude_deg=job["screen_center"][0],
        screen_longitude_deg=job["screen_center"][1],
        title=job["title"],
        evaluation_reference=None,
        on_stage=lambda value: emit(dict(event="stage", **value)),
    )
    if result["status"] != "figures_ready":
        raise ValueError("Complete science and every PNG required: " + str(result["status"]))
    inference = result["inference"]
    packet = result["packet"]
    selected = dict(arms=inference["arms"], owners=inference["owners"])
    projected = ev.project(dict(presentation=packet, selected=selected), None)
    payload = dict(
        schema_version=1,
        model=MODEL,
        policy=request["policy"],
        request=request,
        request_sha256=ev.digest(request),
        provenance=provenance(),
        presentation=packet,
        selected=selected,
        audit=audit_evidence(inference),
        stage_timings=result["stage_timings"],
    )
    raw = pack(payload, result["products"])
    unpack(raw)
    check_scientific_inputs(request)
    if ev.source_binding(source["root"]) != source:
        raise ValueError("Worker source changed during inference")
    if (
        destination.is_relative_to(CACHE)
        and len(raw) + sum(entry.stat().st_size for entry in CACHE.rglob("*") if entry.is_file())
        > 5 * 1024**3
    ):
        raise ValueError("Experimental archive would exceed the authorized 5 GiB cache limit")
    target = destination / "experimental-evidence.zip"
    with target.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    native = payload["provenance"]["native_backend"]["receipts"]
    counts = {
        key: sum(row["counts"].get(key, 0) for row in native)
        for key in sorted({key for row in native for key in row["counts"]})
    }
    summary = dict(
        schema_version=1,
        model=MODEL,
        status="complete",
        role=request["role"],
        policy=request["policy"],
        request_sha256=ev.digest(request),
        source_sha256=source["sha256"],
        native_manifest_sha256=ev.digest(request["native_manifest"]),
        arms=projected,
        prediction_rows=packet["rows"],
        stage_timings=result["stage_timings"],
        native_counts=counts,
        work={
            key: value["counts"]
            for key, value in payload["provenance"].items()
            if key != "native_backend"
        },
        artifact=dict(path=str(target), sha256=ev.file_digest(target), bytes=len(raw)),
        reference_usage="none; worker never receives evaluation coordinates",
    )
    write(destination / "worker-result.json", summary)
    return 0


def inspect_artifact(request, worker):
    codec = ev.owned_import("leo.storage.localization_v3_codec", request["source"])
    payload, _ = codec.unpack(Path(worker["artifact"]["path"]).read_bytes())
    if (
        payload["model"] != MODEL
        or payload["schema_version"] != 1
        or payload["request"] != request
        or payload["request_sha256"] != ev.digest(request)
        or payload["policy"] != request["policy"]
    ):
        raise ValueError("Experimental archive request/policy binding differs")
    projection = ev.project(payload, None)
    if (
        projection != worker["arms"]
        or payload["presentation"]["rows"] != worker["prediction_rows"]
        or payload["stage_timings"] != worker["stage_timings"]
    ):
        raise ValueError("Worker metrics differ from experimental scientific evidence")
    receipts = payload["provenance"]["native_backend"]["receipts"]
    counts = {
        key: sum(row["counts"].get(key, 0) for row in receipts)
        for key in sorted({key for row in receipts for key in row["counts"]})
    }
    work = {
        key: value["counts"]
        for key, value in payload["provenance"].items()
        if key != "native_backend"
    }
    if counts != worker["native_counts"] or work != worker["work"]:
        raise ValueError("Worker accounting differs from experimental scientific evidence")


def inspect_artifact_cached(request, worker):
    output = ev.local_output(request["job"]["output_root"])
    cache = ev.local_output(output / "validated-archive.json")
    if cache.parent != output:
        raise ValueError("Validation cache escaped the worker output directory")
    artifact = worker["artifact"]
    path = ev.local_output(artifact["path"])
    if path.stat().st_size != artifact["bytes"] or ev.file_digest(path) != artifact["sha256"]:
        raise ValueError("Experimental scientific archive changed")
    binding = dict(
        schema_version=1,
        validator_sha256=ev.file_digest(__file__),
        evaluator_sha256=ev.file_digest(ev.__file__),
        request_sha256=ev.digest(request),
        worker_sha256=ev.digest(worker),
        artifact=worker["artifact"],
        policy=request["policy"],
        source_sha256=request["source"]["sha256"],
        native_manifest_sha256=ev.digest(request["native_manifest"]),
        scientific_validation="lossless archive decoded and scientific projection checked",
    )
    receipt = dict(binding, binding_sha256=ev.digest(binding), validated=True)
    if cache.exists():
        try:
            if ev.read(cache) == receipt:
                return "cached"
        except (ValueError, OSError):
            pass
    inspect_artifact(request, worker)
    write(cache, receipt)
    return "fresh"


def validate_record(manifest, assignment, role, record):
    expected = worker_request(manifest, assignment, role)
    if record["request_sha256"] != ev.digest(expected) or record["role"] != role:
        raise ValueError("Saved execution request/role differs")
    if record["status"] not in ("complete", "missing", "failed", "timed_out"):
        raise ValueError("Unknown experimental worker outcome")
    if expected is None:
        if record["status"] != "missing":
            raise ValueError("Unavailable input must remain missing")
        return
    if record["status"] == "complete":
        value = record["worker"]
        if (
            value["model"] != MODEL
            or value["status"] != "complete"
            or value["policy"] != manifest["policies"][role]
            or value["request_sha256"] != ev.digest(expected)
            or value["source_sha256"] != manifest["source"]["sha256"]
            or value["native_manifest_sha256"] != ev.digest(manifest["native_manifest"])
        ):
            raise ValueError("Saved worker scientific binding differs")
        artifact = value["artifact"]
        expected_path = Path(expected["job"]["output_root"]) / "experimental-evidence.zip"
        if artifact["path"] != str(expected_path):
            raise ValueError("Experimental scientific archive changed")
        if set(value["arms"]) != set(ev.ARMS) or set(value["prediction_rows"]) != set(ev.ARMS):
            raise ValueError("Both calibration arms required")
        return inspect_artifact_cached(expected, value)


def measured_arms(worker, reference):
    evidence = dict(
        presentation=dict(arms=worker["arms"]),
        selected=dict(
            arms={
                arm: dict(negative_twice_elbo=worker["arms"][arm]["frequency_score"])
                for arm in ev.ARMS
            },
            owners={arm: worker["arms"][arm]["owners"] for arm in ev.ARMS},
        ),
    )
    return ev.project(evidence, reference)


def supervise_worker(command, log_path, timeout, environment):
    """Reuse the existing descendant discovery and wait4 accounting with an exact deadline."""
    began = time.monotonic()
    forced = False
    with Path(log_path).open("xb") as log:
        child = subprocess.Popen(
            command, stdout=log, stderr=subprocess.STDOUT, env=environment, start_new_session=True
        )
        try:
            while True:
                pid, status, usage = os.wait4(child.pid, os.WNOHANG)
                if pid:
                    child.returncode = os.waitstatus_to_exitcode(status)
                    break
                if not forced and time.monotonic() - began >= timeout:
                    forced = True
                    for pid in ev.descendants(child.pid):
                        with suppress(ProcessLookupError):
                            os.kill(pid, signal.SIGKILL)
                    with suppress(ProcessLookupError):
                        os.killpg(child.pid, signal.SIGKILL)
                time.sleep(0.02)
        finally:
            if child.returncode is None:
                for pid in ev.descendants(child.pid):
                    with suppress(ProcessLookupError):
                        os.kill(pid, signal.SIGKILL)
                child.wait()
    return dict(
        returncode=child.returncode,
        wall_seconds=time.monotonic() - began,
        cpu_seconds=usage.ru_utime + usage.ru_stime,
        cpu_complete=not forced,
        status="timed_out" if forced else "exited",
    )


def common_residuals(left, right, arm):
    a = {row["observation_id"]: row for row in left["prediction_rows"][arm]}
    b = {row["observation_id"]: row for row in right["prediction_rows"][arm]}
    common = sorted(oid for oid in a.keys() & b.keys() if a[oid]["norad"] == b[oid]["norad"])
    for oid in common:
        for key in ("measured_cfo_hz", "receiver", "channel", "time_s"):
            if a[oid][key] != b[oid][key]:
                raise ValueError("Matched observation differs: " + oid)
    return dict(
        count=len(common),
        observation_ids_sha256=ev.digest(common),
        **{
            side: math.sqrt(sum(rows[oid]["residual_hz"] ** 2 for oid in common) / len(common))
            if common
            else None
            for side, rows in (("baseline_rms_hz", a), ("candidate_rms_hz", b))
        },
        interpretation=("same observations and identities; selected-fit residuals, "
                        "not held-out prediction"),
    )


def collect(manifest):
    records, pairs = {}, []
    for assignment in manifest["schedule"]:
        case = assignment["case"]
        folder = Path(manifest["output"]) / (case + "-r" + str(assignment["repetition"]))
        group = records.setdefault((case, assignment["repetition"]), {})
        for role in manifest["roles"]:
            path = folder / (role + "-execution.json")
            if path.exists():
                record = ev.read(path)
                if record["status"] == "started":
                    continue
                validate_record(manifest, assignment, role, record)
                group[role] = record
        for role in manifest["roles"]:
            if role == "baseline":
                continue
            a, b = group.get("baseline"), group.get(role)
            pair = dict(
                case=case,
                dataset=assignment["dataset"],
                repetition=assignment["repetition"],
                group=assignment["group"],
                split=assignment["split"],
                candidate=role,
                baseline_status=a["status"] if a else "absent",
                candidate_status=b["status"] if b else "absent",
            )
            if a and b and a["status"] == b["status"] == "complete":
                reference = manifest["cohorts"][assignment["dataset"]]["references"][case]
                arms_a, arms_b = (
                    measured_arms(a["worker"], reference),
                    measured_arms(b["worker"], reference),
                )
                pair["arms"] = {}
                for arm in ev.ARMS:
                    x, y = arms_a[arm], arms_b[arm]
                    metrics = {}
                    for metric in ev.METRICS:
                        av, bv = x.get(metric), y.get(metric)
                        metrics[metric] = dict(
                            baseline=av,
                            candidate=bv,
                            delta=bv - av if av is not None and bv is not None else None,
                        )
                    metrics["ownership_changes"] = sum(
                        x["owners"].get(k) != y["owners"].get(k)
                        for k in x["owners"].keys() | y["owners"].keys()
                    )
                    metrics["matched_observation_residuals"] = common_residuals(
                        a["worker"], b["worker"], arm
                    )
                    pair["arms"][arm] = metrics
                if a["process"]["cpu_complete"] and b["process"]["cpu_complete"]:
                    pair["timing"] = {
                        metric: dict(
                            baseline=a["process"][metric],
                            candidate=b["process"][metric],
                            delta=b["process"][metric] - a["process"][metric],
                            overhead_percent=100 * (b["process"][metric] / a["process"][metric] - 1)
                            if a["process"][metric] > 0
                            else None,
                        )
                        for metric in ("wall_seconds", "cpu_seconds")
                    }
                pair["native_counts"] = {
                    side: record["worker"]["native_counts"]
                    for side, record in (("baseline", a), ("candidate", b))
                }
                pair["work"] = {
                    side: record["worker"]["work"]
                    for side, record in (("baseline", a), ("candidate", b))
                }
            pairs.append(pair)
    summaries = {}
    for dataset in manifest["cohorts"]:
        for split in ("all", "diagnostic", "development", "untouched"):
            for role in manifest["roles"]:
                if role == "baseline":
                    continue
                usable = [
                    p
                    for p in pairs
                    if p["dataset"] == dataset
                    and p["candidate"] == role
                    and (split == "all" or p["split"] == split)
                ]
                key = dataset + "/" + split + "/" + role
                summaries[key] = dict(
                    expected=len(usable),
                    paired_complete=sum("arms" in p for p in usable),
                    statuses={
                        side: dict(Counter(p[side + "_status"] for p in usable))
                        for side in ("baseline", "candidate")
                    },
                    arms={
                        arm: {
                            metric: {
                                side: ev.distribution(
                                    p["arms"][arm][metric][side] for p in usable if "arms" in p
                                )
                                for side in ("baseline", "candidate", "delta")
                            }
                            for metric in ev.METRICS
                        }
                        for arm in ev.ARMS
                    },
                    timing={
                        metric: {
                            side: ev.distribution(
                                p["timing"][metric][side] for p in usable if "timing" in p
                            )
                            for side in ("baseline", "candidate", "delta", "overhead_percent")
                        }
                        for metric in ("wall_seconds", "cpu_seconds")
                    },
                )
    expected = len(manifest["schedule"]) * len(manifest["roles"])
    finished = sum(len(group) for group in records.values())
    return dict(
        schema_version=1,
        model=MODEL,
        manifest_sha256=ev.digest(manifest),
        expected_workers=expected,
        finished_workers=finished,
        coverage_complete=finished == expected,
        pairs=pairs,
        summaries=summaries,
        execution_mode=manifest["execution_mode"],
        timing_scope=manifest["timing_scope"],
        validation_scope=(
            "fresh archive size and byte hash on every check; scientific decoding and "
            "projection validation cached by validator, request, worker, source, "
            "native and policy hashes"
        ),
        headline_timing_eligible=False,
        note=("Failures, missing inputs and timeouts remain in coverage. "
              "Fit and position accuracy are separate."),
    )


def save_report(manifest):
    result = collect(manifest)
    output = Path(manifest["output"])
    write(output / "comparison.json", result)
    lines = [
        "# Accuracy repair experiment",
        "",
        manifest["execution_mode"] + ".",
        "",
        f"Completed workers {result['finished_workers']}/{result['expected_workers']}.",
        "",
        ("| Dataset / split / candidate | Pairs | c=0 median error change (m) | "
         "Fitted-c median error change (m) | Median worker overhead |"),
        "| --- | ---: | ---: | ---: | ---: |",
    ]

    def number(value, scale=1):
        return "n/a" if value is None else f"{value * scale:.1f}"

    for key, row in result["summaries"].items():
        values = [
            number(row["arms"][arm]["gps_error_km"]["delta"]["median"], 1000) for arm in ev.ARMS
        ]
        overhead = number(row["timing"]["wall_seconds"]["overhead_percent"]["median"])
        lines.append(
            f"| {key} | {row['paired_complete']}/{row['expected']} | "
            f"{values[0]} | {values[1]} | {overhead}% |"
        )
    lines += [
        "",
        ("Negative position changes improve accuracy. Residual and objective changes "
         "are reported separately in comparison.json."),
        ("Matched-observation residuals use the same identities and observations. "
         "They are selected-fit diagnostics, not an independent predictive validation."),
        ("DS29 errors use operator reference coordinates. Diagnostic groups were selected "
         "for debugging and are reported separately from untouched groups."),
        ("Every worker includes both calibration arms, all PNG rendering and experimental "
         "evidence serialization. Public production publication is outside this experiment."),
        ("Every report freshly checks archive size and byte hash. Scientific archive validation "
         "is reused only while the validator and all bound request, worker and implementation "
         "digests match its persisted receipt."),
        "",
    ]
    (output / "report.md").write_text("\n".join(lines))
    return result


def run(manifest_path, cpus, *, max_recordings, max_wall_seconds, reserve_gib=20):
    if (
        max_recordings < 1
        or not math.isfinite(max_wall_seconds)
        or not 1 <= max_wall_seconds <= 1800
        or not math.isfinite(reserve_gib)
        or reserve_gib < 0
    ):
        raise ValueError("A positive recording cap and run budget <=1800 seconds are required")
    requested_cpus = {int(cpu) for cpu in cpus.split(",")}
    if not requested_cpus or not requested_cpus <= os.sched_getaffinity(0):
        raise ValueError("Requested CPUs are unavailable")
    manifest = ev.read(manifest_path)
    output = bulk_output(manifest["output"])
    output.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()
    admitted = set()
    with (output / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        check_bindings(manifest)
        stopped = None
        for assignment in manifest["schedule"]:
            group_key = assignment["dataset"] + ":" + assignment["group"]
            folder = output / (assignment["case"] + "-r" + str(assignment["repetition"]))
            for role in assignment["order"]:
                path = folder / (role + "-execution.json")
                if path.exists():
                    record = ev.read(path)
                    if record["status"] == "started":
                        raise RuntimeError(
                            "Interrupted worker retained for investigation: " + str(path)
                        )
                    validate_record(manifest, assignment, role, record)
                    continue
                if group_key not in admitted and len(admitted) >= max_recordings:
                    stopped = "recording admission limit"
                    break
                if time.monotonic() - began >= max_wall_seconds:
                    stopped = "bounded invocation wall budget"
                    break
                if max_wall_seconds - (time.monotonic() - began) < manifest["timeout_seconds"]:
                    stopped = "insufficient invocation budget for another complete worker deadline"
                    break
                if shutil.disk_usage(output).free / 1024**3 < reserve_gib:
                    stopped = "bulk free-space reserve"
                    break
                if (
                    output.is_relative_to(CACHE)
                    and sum(entry.stat().st_size for entry in CACHE.rglob("*") if entry.is_file())
                    >= 4 * 1024**3
                ):
                    stopped = "bounded cache admission reserve below 1 GiB of the 5 GiB limit"
                    break
                check_bindings(manifest)
                admitted.add(group_key)
                folder.mkdir(parents=True, exist_ok=True)
                request = worker_request(manifest, assignment, role)
                record = dict(
                    status="missing" if request is None else "started",
                    role=role,
                    request_sha256=ev.digest(request),
                    before=host(),
                )
                write(path, record)
                if request is not None:
                    destination = Path(request["job"]["output_root"])
                    destination.mkdir(exist_ok=False)
                    request_path = destination / "experimental-request.json"
                    write(request_path, request)
                    command = [
                        "taskset",
                        "-c",
                        cpus,
                        manifest["python"],
                        "-B",
                        manifest["worker"],
                        "worker",
                        "--request",
                        str(request_path),
                    ]
                    environment = dict(
                        ENVIRONMENT,
                        PYTHONPATH=manifest["source"]["root"]
                        + ":"
                        + str(Path(manifest["worker"]).parent),
                    )
                    timeout = manifest["timeout_seconds"]
                    record["command"] = command
                    record["timeout_seconds"] = timeout
                    record["process"] = supervise_worker(
                        command, destination / "worker.log", timeout, environment
                    )
                    worker_path = destination / "worker-result.json"
                    if record["process"]["status"] == "timed_out":
                        record["status"] = "timed_out"
                    elif record["process"]["returncode"] or not worker_path.exists():
                        record["status"] = "failed"
                    else:
                        record["status"] = "complete"
                        record["worker"] = ev.read(worker_path)
                record["after"] = host()
                write(path, record)
                validate_record(manifest, assignment, role, record)
                print(
                    json.dumps(dict(case=assignment["case"], role=role, status=record["status"])),
                    flush=True,
                )
            if stopped:
                break
            save_report(manifest)
        result = save_report(manifest)
        write(
            output / "invocation.json",
            dict(
                status="complete" if result["coverage_complete"] else "staged",
                stop_reason=stopped,
                admitted_recording_groups=sorted(admitted),
                wall_seconds=time.monotonic() - began,
                coverage_complete=result["coverage_complete"],
                after=host(),
            ),
        )
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--manifest", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    plan.add_argument(
        "--source-root", type=Path, default=Path(__file__).resolve().parents[1] / "src"
    )
    plan.add_argument("--native-manifest", type=Path, required=True)
    plan.add_argument(
        "--cohorts", type=Path, help="JSON mapping DS26/DS29 to snapshot and references paths"
    )
    plan.add_argument("--profile", choices=("diagnostic", "holdout", "full"), default="holdout")
    plan.add_argument("--cases")
    plan.add_argument("--groups-per-dataset", type=int, default=1)
    plan.add_argument(
        "--roles",
        "--variants",
        dest="roles",
        default=",".join(DEFAULT_ROLES),
        help="Comma-separated variants; a fresh baseline is always included",
    )
    plan.add_argument("--seed", default="accuracy-repair-ds26-ds29-20261115-v1")
    plan.add_argument("--repeats", type=int, default=1)
    plan.add_argument("--timeout", type=float, default=1200)
    execute = commands.add_parser("run")
    execute.add_argument("--manifest", type=Path, required=True)
    execute.add_argument("--cpus", required=True)
    execute.add_argument("--max-recordings", type=int, default=1)
    execute.add_argument("--max-wall-seconds", type=float, default=1800)
    execute.add_argument("--reserve-gib", type=float, default=20)
    report = commands.add_parser("report")
    report.add_argument("--manifest", type=Path, required=True)
    worker = commands.add_parser("worker", help=argparse.SUPPRESS)
    worker.add_argument("--request", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == "worker":
        return execute_worker(args.request)
    if args.action == "plan":
        manifest = prepare(args)
        path = bulk_output(args.manifest)
        if path.exists() and ev.read(path) != manifest:
            raise ValueError("Existing frozen manifest differs")
        write(path, manifest)
        print(path)
        return 0
    if args.action == "report":
        manifest = ev.read(args.manifest)
        check_bindings(manifest)
        save_report(manifest)
        return 0
    return run(
        args.manifest,
        args.cpus,
        max_recordings=args.max_recordings,
        max_wall_seconds=args.max_wall_seconds,
        reserve_gib=args.reserve_gib,
    )


if __name__ == "__main__":
    raise SystemExit(main())
