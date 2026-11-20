"""Run the preregistered stored-GLRT compact-finish controls on matching CPUs."""

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

from ..__main__ import (
    DEFAULT_OUT,
    ROOT,
    encoded,
    local_output,
    public_cases,
    references,
    run_one,
    save_json,
    write,
)
from ..scoring import ARMS, distance_km

FULL = "v5_lean"
FINISH = "compact_finish"
CAVITY = "orbit_projector"
RUNS = (
    ("ds26-common127", "DS26-0066", 20, (FULL, FINISH, CAVITY)),
    ("ds26-common127", "DS26-0036", 21, (FINISH, FULL, CAVITY)),
    ("roof16", "DS29-0082", 22, (FULL, FINISH, CAVITY)),
)
ADDITION_CASE = ("ds26-common127", "DS26-0002", 23)
POSITION_LIMIT_M = 1.0
RMS_LIMIT_HZ = 1e-4


def score_case(ref, records):
    records = {r["method"]: r for r in records}
    metrics = {}
    for method, record in records.items():
        result = record["result"]
        metrics[method] = dict(
            status=result["status"],
            wall_s=record["worker_wall_s"],
            cpu_s=record["worker_cpu_s"],
            arms={},
        )
        for arm in ARMS:
            value = result.get("arms", {}).get(arm, {})
            point = value.get("latlon")
            rms = result["metrics"].get(f"{arm}_conditional_rms_hz", value.get("rf_rms_hz"))
            metrics[method]["arms"][arm] = dict(
                latlon=point,
                error_km=distance_km(ref["truth"], point),
                conditional_rms_hz=rms,
                frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
            )
    parity = {}
    for arm in ARMS:
        full, lean = (metrics[k]["arms"][arm] for k in (FULL, FINISH))
        distance = distance_km(full["latlon"], lean["latlon"])
        a, b = full["conditional_rms_hz"], lean["conditional_rms_hz"]
        rms_difference = abs(a - b) if a is not None and b is not None else None
        a, b = full["frequency_score"], lean["frequency_score"]
        objective_difference = abs(a - b) if a is not None and b is not None else None
        parity[arm] = dict(
            coordinate_delta_m=distance * 1000 if distance is not None else None,
            conditional_rms_delta_hz=rms_difference,
            frequency_score_delta=objective_difference,
            passed=(
                distance is not None
                and distance * 1000 <= POSITION_LIMIT_M
                and rms_difference is not None
                and rms_difference <= RMS_LIMIT_HZ
            ),
        )
    return dict(
        id=ref["id"],
        methods=metrics,
        parity=parity,
        speedup={key: metrics[FULL][key] / metrics[FINISH][key] for key in ("wall_s", "cpu_s")},
        finish_increment_s={
            key: metrics[FINISH][key] - metrics[CAVITY][key] for key in ("wall_s", "cpu_s")
        },
    )


def measured(case, method, cpuid, directory):
    # GNU time accounts for the Python worker and its waited numerical processes.
    # The inner runner supplies the same attribution boundary for wall time.
    request, target, timing = (directory / name for name in ("input.json", "result.json", "time"))
    save_json(request, case)
    command = [
        "/usr/bin/time",
        "-f",
        "%U %S",
        "-o",
        str(timing),
        "taskset",
        "-c",
        str(cpuid),
        sys.executable,
        "-B",
        "-m",
        "tools.pipeline_eval.qualification.compact_finish_eval",
        "--worker",
        method,
        str(request),
        str(target),
        str(directory),
        str(cpuid),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    user, system = (float(value) for value in timing.read_text().split())
    record = json.loads(target.read_bytes())
    return dict(record, worker_user_s=user, worker_system_s=system, worker_cpu_s=user + system)


def qualify(output):
    output = local_output(output)
    output.mkdir(parents=True, exist_ok=True)
    if not {row[2] for row in RUNS} <= os.sched_getaffinity(0):
        raise ValueError("qualification requires the three preregistered logical CPUs")

    def series(plan):
        panel, ident, cpu, order = plan
        source, refs = references(panel, [ident])
        (case,) = public_cases(source, refs, DEFAULT_OUT / "inputs")
        for index, method in enumerate(order):
            with TemporaryDirectory(prefix=f"{ident}-{method}-") as temporary:
                result = measured(case, method, cpu, Path(temporary))
            result.update(method=method, cpu=cpu, execution_order=index)
            save_json(output / f"{ident}-{method}.json", result)
            print(
                ident,
                method,
                result["result"]["status"],
                round(result["worker_wall_s"], 2),
                round(result["worker_cpu_s"], 2),
                flush=True,
            )

    with ThreadPoolExecutor(max_workers=len(RUNS)) as pool:
        list(pool.map(series, RUNS))
    return score_receipts(output)


def score_receipts(output):
    summary, records = [], []
    for panel, ident, cpu, order in RUNS:
        _, (ref,) = references(panel, [ident])
        batch = []
        for index, method in enumerate(order):
            record = json.loads((output / f"{ident}-{method}.json").read_bytes())
            observed = tuple(record[k] for k in ("id", "method", "cpu", "execution_order"))
            if observed != (ident, method, cpu, index):
                raise ValueError(f"{ident} receipt differs from the preregistered timing order")
            batch.append(record)
        if len({r["input_sha256"] for r in batch}) != 1:
            raise ValueError(f"{ident} methods ran on different case inputs")
        summary.append(score_case(ref, batch))
        records.extend(batch)
    write(output / "predictions.jsonl", b"".join(encoded(r) + b"\n" for r in records))
    gallery = [r for r in records if r["method"] == FINISH]
    extension = output / f"{ADDITION_CASE[1]}-{FINISH}.json"
    extension_passed = True
    if extension.is_file():
        extension_record = json.loads(extension.read_bytes())
        panel, ident, _ = ADDITION_CASE
        _, (ref,) = references(panel, [ident])
        extension_passed = score_extension(output, ref, archived_final(ident), extension_record)
        gallery.append(extension_record)
    for index, record in enumerate(gallery):
        path = output / f"adapter/{record['id']}.json"
        if path.is_file():
            confirmed = json.loads(path.read_bytes())
            verify_adapter(record, confirmed)
            gallery[index] = confirmed
    write(output / "compact_finish.jsonl", b"".join(encoded(r) + b"\n" for r in gallery))
    save_json(output / "comparison.json", summary)
    return extension_passed and all(
        p["passed"] for score in summary for p in score["parity"].values()
    )


def archived_final(ident):
    import io
    from zipfile import ZipFile

    from ..variants.v5_lean import SOURCE_SHA256
    from .v5_postfit import ARCHIVE, _map, sha256
    from .v5_prefix_audit import value

    directory = ARCHIVE / f"{ident}-r0"
    receipt = json.loads((directory / "baseline-execution.json").read_bytes())
    worker = receipt["worker"]
    raw = (directory / "baseline/experimental-evidence.zip").read_bytes()
    if (
        receipt["role"] != "baseline"
        or receipt["status"] != "complete"
        or worker["source_sha256"] != SOURCE_SHA256
        or worker["artifact"]["sha256"] != sha256(raw)
    ):
        raise ValueError(f"{ident} lacks an intact original v5 result")
    with ZipFile(io.BytesIO(raw)) as archive:
        tree = _map(json.loads(archive.read("values.json"))["tree"])
        if tree["request_sha256"] != receipt["request_sha256"]:
            raise ValueError("Archived trial request binding differs from its worker")
        request = _map(tree["request"])
        job = _map(request["job"])
        input_sha256 = _map(job["native_input"])["sha256"]
        config_sha256 = _map(job["track_config"])["sha256"]
        snapshots_sha256 = sha256(encoded(_map(request["causal_snapshots"])))
        audit = _map(tree["audit"])
        addition = _map(_map(audit["additional_position"])["recovery"])
        decision = _map(_map(addition["decisions"])["72h_30s"])
        final = _map(_map(audit["reassociation_complete"])["recovery"])
        arms = {}
        for arm, node in _map(_map(tree["selected"])["arms"]).items():
            item = _map(node)
            arms[arm] = dict(
                latlon=value(item["endpoint_latlon"], archive),
                conditional_rms_hz=value(item.get("RMS_hz", item.get("rms_hz")), archive),
                frequency_score=value(
                    item.get("negative_twice_elbo", item.get("objective")), archive
                ),
                presentation_residual_rms_hz=worker["arms"][arm]["residual_rms_hz"],
            )
    return dict(
        id=ident,
        arms=arms,
        addition_status=decision["status"],
        addition_norad=decision.get("norad"),
        reassociation_selected=final["selected"],
        input_sha256=input_sha256,
        track_config_sha256=config_sha256,
        causal_snapshots_sha256=snapshots_sha256,
        archive_sha256=worker["artifact"]["sha256"],
        stage_s={t["stage"]: t["seconds"] for t in worker["stage_timings"]},
    )


def qualify_extension(output):
    from .v5_postfit import sha256

    output = local_output(output)
    panel, ident, cpu = ADDITION_CASE
    source, (ref,) = references(panel, [ident])
    (case,) = public_cases(source, [ref], DEFAULT_OUT / "inputs")
    archived = archived_final(ident)
    if archived["input_sha256"] != case["native_sha256"]:
        raise ValueError("Archived control and compact finish use different native observations")
    request = json.loads(Path(case["request_path"]).read_bytes())
    track_config = request["job"]["track_config"]["sha256"]
    snapshots = sha256(encoded(request["causal_snapshots"]))
    if (archived["track_config_sha256"], archived["causal_snapshots_sha256"]) != (
        track_config,
        snapshots,
    ):
        raise ValueError("Archived control and compact finish have different scientific bindings")
    if archived["addition_status"] != "qualified" or archived["reassociation_selected"] is not None:
        raise ValueError("The extension must exercise the frozen conditional-addition decision")
    with TemporaryDirectory(prefix=f"{ident}-compact-finish-") as directory:
        record = measured(case, FINISH, cpu, Path(directory))
    record.update(method=FINISH, cpu=cpu)
    save_json(output / f"{ident}-{FINISH}.json", record)
    write(output / "compact_finish_addition.jsonl", encoded(record) + b"\n")
    return score_extension(output, ref, archived, record)


def score_extension(output, ref, archived, record):
    captured = record["result"]
    comparisons = {}
    for arm in ARMS:
        expected, fresh = archived["arms"][arm], captured.get("arms", {}).get(arm, {})
        if expected["latlon"] != ref["reference"]["baseline"][arm]["latlon"]:
            raise ValueError("Archived control differs from the frozen scoring reference")
        point = fresh.get("latlon")
        delta = distance_km(expected["latlon"], point)
        rms = captured["metrics"].get(f"{arm}_conditional_rms_hz")
        objective = captured["metrics"].get(f"{arm}_frequency_score")
        expected_rms = expected["conditional_rms_hz"]
        rms_delta = (
            abs(expected_rms - rms) if expected_rms is not None and rms is not None else None
        )
        score_delta = (
            abs(expected["frequency_score"] - objective) if objective is not None else None
        )
        comparisons[arm] = dict(
            latlon=point,
            error_km=distance_km(ref["truth"], point),
            coordinate_delta_m=delta * 1000 if delta is not None else None,
            conditional_rms_hz=rms,
            conditional_rms_delta_hz=rms_delta,
            frequency_score=objective,
            frequency_score_delta=score_delta,
            passed=(
                delta is not None
                and delta * 1000 <= POSITION_LIMIT_M
                and (
                    (rms_delta is not None and rms_delta <= RMS_LIMIT_HZ)
                    or (expected_rms is None and rms is None)
                )
                and score_delta is not None
                and score_delta <= 1e-4
            ),
        )
    save_json(output / "addition-extension.json", dict(archive=archived, comparisons=comparisons))
    return captured["metrics"].get("addition_status") == "qualified" and all(
        row["passed"] for row in comparisons.values()
    )


def confirm_adapter(output, ident):
    output = local_output(output)
    panel, _, cpu, *_ = next(row for row in (*RUNS, ADDITION_CASE) if row[1] == ident)
    prior = json.loads((output / f"{ident}-{FINISH}.json").read_bytes())
    if prior["cpu"] != cpu:
        raise ValueError("The adapter check must use the original pinned CPU")
    source, refs = references(panel, [ident])
    (case,) = public_cases(source, refs, DEFAULT_OUT / "inputs")
    with TemporaryDirectory(prefix=f"{ident}-adapter-") as directory:
        fresh = measured(case, FINISH, cpu, Path(directory))
    fresh.update(method=FINISH, cpu=cpu, qualification="adapter_confirmation")
    save_json(output / f"adapter/{ident}.json", fresh)
    verify_adapter(prior, fresh)
    print(
        ident,
        "adapter",
        round(fresh["worker_wall_s"], 2),
        round(fresh["worker_cpu_s"], 2),
        flush=True,
    )
    return True


def verify_adapter(prior, fresh):
    a, b = (r["result"] for r in (prior, fresh))
    keys = [
        "addition_status",
        "reassociation_targets",
        "reassociation_admitted",
        "reassociation_selected",
        "observations",
        "tracks",
        *(
            f"{arm}_{name}"
            for arm in ARMS
            for name in ("frequency_score", "conditional_rms_hz", "associated_observations")
        ),
    ]
    if (
        prior["input_sha256"] != fresh["input_sha256"]
        or a["status"] != "ok"
        or b["status"] != "ok"
        or a["arms"] != b["arms"]
        or any(a["metrics"].get(key) != b["metrics"].get(key) for key in keys)
    ):
        raise ValueError(f"{fresh['id']} adapter changed the qualified scientific result")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--worker", nargs=5, help=argparse.SUPPRESS)
    parser.add_argument("--addition-extension", action="store_true")
    parser.add_argument("--score-only", action="store_true")
    parser.add_argument("--confirm-adapter", choices=[r[1] for r in (*RUNS, ADDITION_CASE)])
    args = parser.parse_args()
    if args.worker:
        method, request, target, directory, cpu = args.worker
        case = json.loads(Path(request).read_bytes())
        save_json(Path(target), run_one(method, case, Path(directory), 1200, int(cpu)))
    elif args.out is None:
        parser.error("--out is required")
    elif args.score_only:
        return 0 if score_receipts(args.out) else 1
    elif args.confirm_adapter:
        return 0 if confirm_adapter(args.out, args.confirm_adapter) else 1
    else:
        return 0 if (qualify_extension if args.addition_extension else qualify)(args.out) else 1


if __name__ == "__main__":
    sys.exit(main())
