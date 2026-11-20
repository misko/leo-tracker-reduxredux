"""Run compact v5 on full and 180-second archived observation streams."""

import argparse
import gzip
import json
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from time import perf_counter

from ..__main__ import encoded, local_output, write
from ..scoring import ARMS, distance_km, validate_result
from ..variants import contiguous_prefix as prefix
from ..variants import orbit_projector, v5_core
from .full_v5_check import BULK, FROZEN, _load_case, _sha
from .prefix_figures import TIMING_IDS
from .recording_to_v5 import bind_request, save

ORDERS = {
    case_id: ("prefix", "full") if i % 2 == 0 else ("full", "prefix")
    for i, case_id in enumerate(TIMING_IDS)
}


def seal():
    sources = (prefix.__file__, v5_core.__file__, orbit_projector.__file__, orbit_projector.KERNEL)
    return dict(
        cutoff_seconds=prefix.PREFIX_SECONDS,
        matched_order=ORDERS,
        source_sha256={Path(path).name: _sha(Path(path)) for path in sources},
    )


def solver_cpu():
    usage = getrusage(RUSAGE_CHILDREN)
    return usage.ru_utime + usage.ru_stime


def normalized(case, data):
    return dict(
        data,
        native_sha256=case["native"]["sha256"],
        catalog_sha256=case["catalog"]["sha256"],
    )


def position(case, path, output, metrics, variant):
    experiment = bind_request(case, path, output / "experimental-request.json")
    started, cpu = perf_counter(), solver_cpu()
    result = prefix.run(experiment, output / "position")
    elapsed, consumed = perf_counter() - started, solver_cpu() - cpu
    outcome = result["metrics"]
    if "causal_cutoff_utc_ns" in outcome and (
        outcome["causal_cutoff_utc_ns"] != case["cutoff_utc_ns"]
        or outcome["causal_cutoff_utc_ns"] != metrics["before_bracket_utc_ns"]
        or outcome["prepared_duration_s"] != metrics["last_input_sample_s"]
    ):
        raise ValueError("rebuilt position inputs changed the recording clock authority")
    remaining_at_last_input_s = (
        metrics["full_input_delivery_elapsed_s"][0] - metrics["last_input_delivery_elapsed_s"][0]
    )
    outcome.update(
        metrics,
        solver_cpu_s=consumed,
        input_to_recording_end_s=remaining_at_last_input_s,
        ideal_overlapped_fix_elapsed_s=[
            v + elapsed for v in metrics["last_input_delivery_elapsed_s"]
        ],
        ideal_overlapped_fix_before_original_end=(
            result["status"] == "ok" and elapsed <= remaining_at_last_input_s
        ),
    )
    validate_result(result)
    data = dict(
        id=case["id"],
        variant=variant,
        result=result,
        inference_factor_sha256=_sha(path),
        cpu=min(os.sched_getaffinity(0)),
        worker_wall_s=elapsed,
    )
    data = normalized(case, data)
    save(output / "prediction.json", data)
    return data


def pair(case_id, output, expected):
    if json.loads(expected.read_bytes()) != json.loads(encoded(seal())):
        raise ValueError("contiguous-prefix policy differs from the preregistered source seal")
    case = _load_case(case_id)
    locator = case["native"]
    path = BULK / locator["path"]
    if _sha(path) != locator["sha256"]:
        raise ValueError("frozen capture-era factors changed")
    original = json.loads(path.read_bytes())
    output.mkdir(parents=True, exist_ok=False)
    for mode in ORDERS[case_id]:
        destination = output / mode
        destination.mkdir()
        view, metrics = prefix.restrict(original, prefix=mode == "prefix")
        source = path
        if mode == "prefix":
            source = destination / "native.json"
            save(source, view)
        data = position(case, source, destination, metrics, "capture-era-" + mode)
        print(case_id, mode, data["result"]["status"], data["worker_wall_s"], flush=True)
    if json.loads(expected.read_bytes()) != json.loads(encoded(seal())):
        raise ValueError("recorded prefix trial sources changed during inference")


def score(output, recordings):
    """Score the positions only after prediction receipts are complete."""
    path = FROZEN / "targets.jsonl"
    if _sha(path) != json.loads((FROZEN / "provenance.json").read_bytes())["files"][path.name]:
        raise ValueError("frozen scoring roster changed")
    with path.open() as stream:
        targets = {
            row["id"]: row["truth"] for row in map(json.loads, stream) if row["id"] in TIMING_IDS
        }
    rows = []
    receipts = {"full": [], "prefix": []}
    for case_id in TIMING_IDS:
        cases = {
            mode: json.loads((recordings / case_id / mode / "prediction.json").read_bytes())
            for mode in ("full", "prefix")
        }
        if any(case["id"] != case_id for case in cases.values()):
            raise ValueError("position receipt belongs to a different recording")
        for case in cases.values():
            validate_result(case["result"])
        sealed = _load_case(case_id)
        for mode, record in cases.items():
            receipts[mode].append(encoded(normalized(sealed, record)) + b"\n")
        full, early = (cases[mode]["result"] for mode in ("full", "prefix"))
        pair_audit = {}
        for key in ("causal_cutoff_utc_ns", "catalogue_latest_sha256"):
            pair_audit[key + "_matched"] = full["metrics"].get(key) == early["metrics"].get(key)
        if not all(pair_audit.values()):
            raise ValueError("paired cavity comparisons used different causal catalogues")
        rows.append(
            dict(
                id=case_id,
                **pair_audit,
                arms={
                    arm: dict(
                        full_error_km=distance_km(full["arms"][arm]["latlon"], targets[case_id]),
                        prefix_error_km=distance_km(early["arms"][arm]["latlon"], targets[case_id]),
                        displacement_km=distance_km(
                            full["arms"][arm]["latlon"], early["arms"][arm]["latlon"]
                        ),
                        full_rf_rms_hz=full["arms"][arm].get("rf_rms_hz"),
                        prefix_rf_rms_hz=early["arms"][arm].get("rf_rms_hz"),
                    )
                    for arm in ARMS
                },
            )
        )
    for mode in ("full", "prefix"):
        packed = b"".join(receipts[mode])
        write(output / (mode + "-positions.jsonl.gz"), gzip.compress(packed, mtime=0))
    write(output / "scores.json", json.dumps(rows, indent=2).encode() + b"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=local_output)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("seal")
    paired = actions.add_parser("pair")
    paired.add_argument("case", choices=TIMING_IDS)
    paired.add_argument("--seal", required=True, type=Path)
    scoring = actions.add_parser("score")
    scoring.add_argument("recordings", type=Path)
    args = parser.parse_args()
    if args.action == "seal":
        save(args.out, seal())
    elif args.action == "pair":
        if len(os.sched_getaffinity(0)) != 1:
            parser.error("pin the matched case to one CPU")
        pair(args.case, args.out, args.seal)
    else:
        score(args.out, args.recordings)


if __name__ == "__main__":
    main()
