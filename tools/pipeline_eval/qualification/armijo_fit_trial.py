"""Benchmark a smaller bounded position solver against the sealed v5 controls."""

import argparse
import gzip
import json
import os
from pathlib import Path
from time import perf_counter

from ..__main__ import encoded, local_output, read_predictions, write
from ..scoring import ARMS, distance_km, validate_result
from ..variants import v5_armijo_fit as armijo
from ..variants import v5_lean
from ..variants import v5_secant_fit as secant
from .full_v5_check import BULK, FROZEN, REPO, _load_case, _sha
from .recording_to_v5 import bind_request, save
from .secant_fit_trial import CASE_LIMIT_S, LANES, bind_record, failed_result

CONTROL = REPO / "reports/2026_11_19_receiver_convergence/position-fit"
CPUS = {case: 20 + i for i, lane in enumerate(LANES) for case in lane}
PLAN = dict.fromkeys(CPUS, ("armijo",))
PLAN.update({"DS26-0036": ("armijo", "fresh-secant"), "DS29-0082": ("fresh-secant", "armijo")})
LABELS = {"armijo": "v5_armijo_fit", "fresh-secant": "v5_secant_fit"}


def source_seal(controls):
    lock = json.loads((controls / "prediction-lock.json").read_bytes())
    prior = json.loads((controls / "seal.json").read_bytes())
    if (
        set(lock["cases"]) != set(PLAN)
        or lock["source_seal_sha256"] != _sha(controls / "seal.json")
        or prior["frozen_v5_sha256"] != v5_lean.SOURCE_SHA256
    ):
        raise ValueError("archived controls do not bind the matched source and recording roster")
    sources = Path(armijo.__file__).parent
    if any(
        _sha(sources / name) != digest for name, digest in prior["compact_source_sha256"].items()
    ):
        raise ValueError("compact cavity source differs from the archived controls")
    return dict(
        cases=list(PLAN),
        execution_order=PLAN,
        cpus=CPUS,
        case_limit_s=CASE_LIMIT_S,
        armijo_source_sha256=_sha(Path(armijo.__file__)),
        stop_km=armijo.STOP_KM,
        line_trials=armijo.TRIALS,
        armijo_factor=armijo.ARMIJO,
        control_lock_sha256=_sha(controls / "prediction-lock.json"),
        control_source_seal_sha256=lock["source_seal_sha256"],
    )


def control_predictions(controls):
    lock = json.loads((controls / "prediction-lock.json").read_bytes())
    data = {}
    for mode in ("reference", "secant"):
        name = f"{mode}-positions.jsonl.gz"
        if _sha(controls / name) != lock["files"][name]:
            raise ValueError("archived control predictions changed")
        rows = read_predictions(controls / name)
        if set(rows) != set(PLAN):
            raise ValueError("archived control roster changed")
        for case_id, row in rows.items():
            binding = bind_record(_load_case(case_id), mode, controls / "seal.json")
            if (
                row.get("cpu") != CPUS[case_id]
                or row["result"]["status"] != "ok"
                or any(row.get(key) != value for key, value in binding.items())
            ):
                raise ValueError(f"{case_id} archived control differs from the matched input")
        data[mode] = rows
    return data


def candidate_binding(case, mode, seal):
    return dict(bind_record(case, "reference", seal), variant=LABELS[mode])


def run_pair(case_id, output, controls, seal):
    expected = json.loads(seal.read_bytes())
    if expected != json.loads(encoded(source_seal(controls))):
        raise ValueError("optimizer sources differ from the run seal")
    control_predictions(controls)
    if os.sched_getaffinity(0) != {CPUS[case_id]}:
        raise ValueError("use the predeclared pinned CPU for this case")
    start = perf_counter()
    case = _load_case(case_id)
    path = BULK / case["native"]["path"]
    if _sha(path) != case["native"]["sha256"]:
        raise ValueError("native input differs from frozen case")
    output.mkdir(parents=True, exist_ok=False)
    experiment = bind_request(case, path, output / "experimental-request.json")
    for mode in PLAN[case_id]:
        remaining = int(CASE_LIMIT_S - (perf_counter() - start))
        began = perf_counter()
        if remaining < 1:
            result = failed_result("timed_out", "paired 480-second run budget exhausted")
        else:
            timeout = v5_lean.TIMEOUT_S
            try:
                v5_lean.TIMEOUT_S = remaining
                directory = output / mode
                result = (
                    armijo.run(experiment, directory)
                    if mode == "armijo"
                    else secant.run(experiment, directory, "secant")
                )
                if "exceeded its " in result.get("reason", ""):
                    result["status"] = "timed_out"
            finally:
                v5_lean.TIMEOUT_S = timeout
        validate_result(result)
        row = dict(
            candidate_binding(case, mode, seal),
            result=result,
            cpu=CPUS[case_id],
            worker_wall_s=perf_counter() - began,
        )
        save(output / f"{mode}-prediction.json", row)
        print(case_id, mode, result["status"], row["worker_wall_s"], flush=True)
    if expected != json.loads(encoded(source_seal(controls))):
        raise ValueError("optimizer sources changed during the run")


def result_record(case, mode, source, seal):
    binding = candidate_binding(case, mode, seal)
    path = source / case["id"] / f"{mode}-prediction.json"
    if not path.exists():
        return dict(
            binding,
            worker_wall_s=None,
            result=failed_result("missing", "no sealed worker result for the scheduled attempt"),
        )
    row = json.loads(path.read_bytes())
    if any(row.get(key) != value for key, value in binding.items()):
        raise ValueError("position receipt differs from the sealed inputs and candidate")
    validate_result(row["result"])
    return row


def compare(reference, candidate, truth):
    first, second = (x["result"] for x in (reference, candidate))
    arms = {}
    for arm in ARMS:
        a, b = (row["arms"][arm] for row in (first, second))
        rms_a, rms_b = a.get("rf_rms_hz"), b.get("rf_rms_hz")
        delta_rms = None if None in (rms_a, rms_b) else rms_b - rms_a
        delta_km = distance_km(a["latlon"], b["latlon"])
        arms[arm] = dict(
            control_error_km=distance_km(a["latlon"], truth),
            armijo_error_km=distance_km(b["latlon"], truth),
            control_rf_rms_hz=rms_a,
            armijo_rf_rms_hz=rms_b,
            endpoint_shift_m=None if delta_km is None else delta_km * 1000,
            rf_rms_delta_hz=delta_rms,
            meets_numerical_limits=(
                delta_km is not None
                and delta_km <= 0.050
                and delta_rms is not None
                and abs(delta_rms) <= 1.0
            ),
        )
    ready = first["status"] == second["status"] == "ok"
    keys = ("tracks", "observations", "cavity_offered", "initial_phase_refresh_counts")
    return dict(
        control_status=first["status"],
        armijo_status=second["status"],
        arms=arms,
        matched_inventory=ready
        and all(
            key in first["metrics"] and first["metrics"][key] == second["metrics"].get(key)
            for key in keys
        ),
        control_worker_wall_s=reference["worker_wall_s"],
        armijo_worker_wall_s=candidate["worker_wall_s"],
    )


def score(output, source, controls, seal):
    locked = json.loads(seal.read_bytes())
    if locked["control_lock_sha256"] != _sha(controls / "prediction-lock.json") or locked[
        "control_source_seal_sha256"
    ] != _sha(controls / "seal.json"):
        raise ValueError("control archive differs from the preregistered comparison")
    archived = control_predictions(controls)
    targets = FROZEN / "targets.jsonl"
    expected = json.loads((FROZEN / "provenance.json").read_bytes())["files"][targets.name]
    if _sha(targets) != expected:
        raise ValueError("scoring targets differ from the frozen inventory")
    with targets.open() as stream:
        truth = {row["id"]: row["truth"] for row in map(json.loads, stream) if row["id"] in PLAN}
    armijo_rows, paired, scores = [], [], []
    for ident, order in PLAN.items():
        case = _load_case(ident)
        current = result_record(case, "armijo", source, seal)
        armijo_rows.append(current)
        row = dict(
            id=ident,
            reference=compare(archived["reference"][ident], current, truth[ident]),
            secant=compare(archived["secant"][ident], current, truth[ident]),
        )
        if "fresh-secant" in order:
            fresh = result_record(case, "fresh-secant", source, seal)
            paired.append(fresh)
            row["fresh_secant"] = compare(fresh, current, truth[ident])
        scores.append(row)

    def pack(name, rows):
        path = output / name
        write(path, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))
        return _sha(path)

    files = {"armijo-positions.jsonl.gz": pack("armijo-positions.jsonl.gz", armijo_rows)}
    for mode in archived:
        name = f"{mode}-positions.jsonl.gz"
        write(output / name, (controls / name).read_bytes())
        files[name] = _sha(output / name)
    fresh_name = "fresh-secant-positions.jsonl.gz"
    prediction_lock = dict(
        cases=list(PLAN),
        files=files,
        source_seal_sha256=_sha(seal),
        control_source_seal_sha256=locked["control_source_seal_sha256"],
        paired_timing=dict(
            cases=[row["id"] for row in paired], files={fresh_name: pack(fresh_name, paired)}
        ),
    )
    write(output / "prediction-lock.json", encoded(prediction_lock) + b"\n")
    write(output / "scores.json", json.dumps(scores, indent=2, allow_nan=False).encode() + b"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controls", default=CONTROL, type=Path)
    parser.add_argument("--out", required=True, type=local_output)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("seal")
    pair = actions.add_parser("pair")
    pair.add_argument("case", choices=PLAN)
    pair.add_argument("--seal", required=True, type=Path)
    decide = actions.add_parser("score")
    decide.add_argument("--source", required=True, type=Path)
    decide.add_argument("--seal", required=True, type=Path)
    args = parser.parse_args()
    if args.action == "seal":
        control_predictions(args.controls)
        save(args.out, source_seal(args.controls))
    elif args.action == "pair":
        run_pair(args.case, args.out, args.controls, args.seal)
    else:
        score(args.out, args.source, args.controls, args.seal)


if __name__ == "__main__":
    main()
