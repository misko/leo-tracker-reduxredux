"""Measure both position optimizers at the same compact v5 boundary."""

import argparse
import gzip
import json
import os
from pathlib import Path
from time import perf_counter

from ..__main__ import encoded, local_output, write
from ..scoring import ARMS, distance_km, validate_result
from ..variants import orbit_projector, v5_core, v5_lean
from ..variants import v5_secant_fit as secant
from .full_v5_check import BULK, FROZEN, _load_case, _sha
from .recording_to_v5 import bind_request, save

LANES = (
    ("DS26-0036", "DS26-0122", "DS29-0174"),
    ("DS29-0082", "DS26-0237", "DS29-0247"),
)
METHODS = ("reference", "secant")
ORDERS = {
    case: METHODS if (lane + index) % 2 == 0 else METHODS[::-1]
    for lane, cases in enumerate(LANES)
    for index, case in enumerate(cases)
}
VARIANTS = {"reference": "compact-v5-bounded-gn", "secant": "v5_secant_fit"}
CASE_LIMIT_S = 480


def source_seal():
    files = (Path(m.__file__) for m in (secant, orbit_projector, v5_core, v5_lean))
    return dict(
        roster=ORDERS,
        pair_limit_s=CASE_LIMIT_S,
        stop_km=secant.STOP_KM,
        optimizer_trials=secant.TRIALS,
        secant_update_limit=secant.SECANT_LIMIT,
        compact_source_sha256={f.name: _sha(f) for f in (*files, orbit_projector.KERNEL)},
        frozen_v5_sha256=v5_lean.SOURCE_SHA256,
    )


def failed_result(status, reason):
    return dict(
        status=status,
        reason=reason,
        boundary=secant.BOUNDARY,
        metrics={},
        arms={arm: dict(latlon=None) for arm in ARMS},
    )


def bind_record(case, mode, seal):
    return dict(
        id=case["id"],
        variant=VARIANTS[mode],
        native_sha256=case["native"]["sha256"],
        catalog_sha256=case["catalog"]["sha256"],
        input_sha256=case["request"]["sha256"],
        source_seal_sha256=_sha(seal),
    )


def run_pair(case_id, output, seal):
    if json.loads(seal.read_bytes()) != json.loads(encoded(source_seal())):
        raise ValueError("position optimizer differs from the preregistered source lock")
    start = perf_counter()
    case = _load_case(case_id)
    native = BULK / case["native"]["path"]
    if _sha(native) != case["native"]["sha256"]:
        raise ValueError("native factors differ from their frozen input binding")
    output.mkdir(parents=True, exist_ok=False)
    experiment = bind_request(case, native, output / "experimental-request.json")
    for mode in ORDERS[case_id]:
        remaining = int(CASE_LIMIT_S - (perf_counter() - start))
        began = perf_counter()
        if remaining < 1:
            result = failed_result("timed_out", "480-second paired deadline exhausted")
        else:
            timeout = v5_lean.TIMEOUT_S
            try:
                v5_lean.TIMEOUT_S = remaining
                result = secant.run(experiment, output / mode, mode)
                if "exceeded its " in result.get("reason", ""):
                    result["status"] = "timed_out"
            finally:
                v5_lean.TIMEOUT_S = timeout
        validate_result(result)
        data = dict(
            bind_record(case, mode, seal),
            result=result,
            cpu=min(os.sched_getaffinity(0)),
            worker_wall_s=perf_counter() - began,
        )
        save(output / f"{mode}-prediction.json", data)
        print(case_id, mode, result["status"], data["worker_wall_s"], flush=True)
    if json.loads(seal.read_bytes()) != json.loads(encoded(source_seal())):
        raise ValueError("position optimizer sources changed during the pair")


def _prediction(case, mode, source, seal):
    receipt = source / case["id"] / f"{mode}-prediction.json"
    binding = bind_record(case, mode, seal)
    if not receipt.exists():
        return dict(
            binding,
            worker_wall_s=None,
            result=failed_result("missing", "no sealed position receipt for this attempt"),
        )
    record = json.loads(receipt.read_bytes())
    if any(record.get(k) != value for k, value in binding.items()):
        raise ValueError("position receipt differs from the sealed input or optimizer")
    validate_result(record["result"])
    if mode == "reference":
        optimizer = record["result"]["metrics"].get("position_optimizer", {})
        for key in ("jacobian_refreshes", "secant_updates", "rejected_trials"):
            optimizer.pop(key, None)
    return record


def score(output, source, seal):
    """Score both calibration arms after completing the frozen position runs."""
    path = FROZEN / "targets.jsonl"
    expected = json.loads((FROZEN / "provenance.json").read_bytes())["files"][path.name]
    if _sha(path) != expected:
        raise ValueError("frozen position reference inputs changed")
    with path.open() as stream:
        truth = {row["id"]: row["truth"] for row in map(json.loads, stream) if row["id"] in ORDERS}
    all_rows, scored = {mode: [] for mode in METHODS}, []
    for ident in ORDERS:
        case = _load_case(ident)
        pair = [_prediction(case, mode, source, seal) for mode in METHODS]
        for mode, row in zip(METHODS, pair, strict=True):
            all_rows[mode].append(encoded(row) + b"\n")
        base, new = (row["result"] for row in pair)
        compare = {}
        for arm in ARMS:
            original, modified = (row["arms"][arm] for row in (base, new))
            orig_rms, new_rms = original.get("rf_rms_hz"), modified.get("rf_rms_hz")
            shift_km = distance_km(original["latlon"], modified["latlon"])
            delta_hz = None if None in (orig_rms, new_rms) else new_rms - orig_rms
            compare[arm] = dict(
                reference_error_km=distance_km(original["latlon"], truth[ident]),
                secant_error_km=distance_km(modified["latlon"], truth[ident]),
                endpoint_shift_m=None if shift_km is None else 1000 * shift_km,
                reference_rf_rms_hz=orig_rms,
                secant_rf_rms_hz=new_rms,
                rf_rms_delta_hz=delta_hz,
                within_numerical_limits=(
                    shift_km is not None
                    and shift_km <= 0.050
                    and delta_hz is not None
                    and abs(delta_hz) <= 1.0
                ),
            )
        scored.append(
            dict(
                id=ident, status=dict(reference=base["status"], secant=new["status"]), arms=compare
            )
        )
    files = {}
    for mode, data in all_rows.items():
        path = output / f"{mode}-positions.jsonl.gz"
        write(path, gzip.compress(b"".join(data), mtime=0))
        files[path.name] = _sha(path)
    lock = dict(source_seal_sha256=_sha(seal), files=files, cases=list(ORDERS))
    write(output / "prediction-lock.json", encoded(lock) + b"\n")
    write(output / "scores.json", json.dumps(scored, indent=2, allow_nan=False).encode() + b"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=local_output)
    action = parser.add_subparsers(dest="action", required=True)
    action.add_parser("seal")
    pair = action.add_parser("pair")
    pair.add_argument("case", choices=ORDERS)
    pair.add_argument("--seal", required=True, type=Path)
    scoring = action.add_parser("score")
    scoring.add_argument("--source", required=True, type=Path)
    scoring.add_argument("--seal", required=True, type=Path)
    args = parser.parse_args()
    if args.action == "seal":
        save(args.out, source_seal())
    elif args.action == "pair":
        if len(os.sched_getaffinity(0)) != 1:
            parser.error("pin each pair to one CPU")
        run_pair(args.case, args.out, args.seal)
    else:
        score(args.out, args.source, args.seal)


if __name__ == "__main__":
    main()
