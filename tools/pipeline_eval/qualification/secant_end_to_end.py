"""Measure one uninterrupted ordinary IQ-to-secant position replay per recording."""

import argparse
import gzip
import json
import os
from hashlib import sha256
from pathlib import Path
from resource import RUSAGE_CHILDREN, RUSAGE_SELF, getrusage
from time import perf_counter

from ..__main__ import encoded, local_output, read_predictions, references, save_json, write
from ..scoring import ARMS, ROLES, distance_km, validate_result
from ..variants import orbit_projector, v5_lean
from . import raw_robust, recording_to_v5, secant_fit_trial
from .full_v5_check import NATIVE_LIBRARY, REPO, _load_case, _sha
from .prefix_figures import csv_file
from .secant_end_to_end_worker import cpu_s, stamp

CASES = ("DS26-0036", "DS29-0082")
CAP_S = 540
FIT_WORKER = Path(__file__).with_name("secant_end_to_end_worker.py")
SOURCE = REPO / "reports/2026_11_19_receiver_convergence/position-fit/seal.json"
HISTORICAL = raw_robust.REPORT / "raw-robust"
METHODS = {
    "secant": ("v5_secant_fit", "positions.jsonl.gz"),
    "reference": ("orbit_projector", "stock-positions.jsonl.gz"),
}
CHAIN_BOUNDARY = "Fresh whole recorded IQ through ordinary native GLRT and secant compact v5 cavity"
STOCK_BOUNDARY = "Exact fresh ordinary native factor file through stock compact v5 cavity"


def preflight(case_id, library):
    if json.loads(SOURCE.read_bytes()) != json.loads(encoded(secant_fit_trial.source_seal())):
        raise ValueError("secant or compact solver differs from the locked qualification")
    lock = json.loads((HISTORICAL / "prediction-lock.json").read_bytes())
    path = HISTORICAL / "positions.jsonl.gz"
    if _sha(path) != lock["files"][path.name]:
        raise ValueError("prior full IQ qualification changed")
    prior = read_predictions(path)[case_id]
    raw = prior["acquisition"]
    if (
        prior["variant"] != "fresh-iq"
        or not raw["exact_prior_native"]
        or raw["detector_sha256"] != "sha256:" + _sha(library)
        or raw["recording_windows"] != _load_case(case_id)["recording"]["window_count"]
    ):
        raise ValueError("no verified complete prior IQ receipt for this acquisition")
    return prior


def capture_duration(document):
    start = document["clock_anchor"]["sample_counter"]
    return (document["last_sample_counter"] - start) / document["source"]["sample_rate_hz"]


def remaining(start):
    return max(0, int(CAP_S - (perf_counter() - start)) - 3)


def profile_fit(case, path, binding, directory, mode, start):
    out = directory / mode
    out.mkdir()
    library = out / "orbit_projector.so"
    stage_wall, stage_cpu = perf_counter(), cpu_s()
    budget = remaining(start)
    if budget < 1:
        result = secant_fit_trial.failed_result("timed_out", "540 s bound exhausted before fit")
    else:
        orbit_projector.compile_kernel(library)
        timeout = v5_lean.TIMEOUT_S
        try:
            v5_lean.TIMEOUT_S = budget
            result = v5_lean.run_bound_worker(
                binding, out, FIT_WORKER, worker_args=(str(library), mode)
            )
        finally:
            v5_lean.TIMEOUT_S = timeout
        if "exceeded its " in result.get("reason", ""):
            result["status"] = "timed_out"
        request = json.loads((out / "request.json").read_bytes())["job"]
        if (
            request["native_input"]["sha256"] != binding["native_sha256"]
            or Path(request["native_input"]["path"]) != path
            or request["evaluation_reference"] is not None
        ):
            raise ValueError("numerical solver did not consume the freshly authenticated factors")
    duration = stamp(stage_wall, stage_cpu)
    result["boundary"] = CHAIN_BOUNDARY if mode == "secant" else STOCK_BOUNDARY
    validate_result(result)
    return dict(
        id=case["id"],
        method=METHODS[mode][0],
        mode="matched-tile",
        variant="fresh-iq-to-position" if mode == "secant" else "same-fresh-factors-stock-fit",
        native_sha256=binding["native_sha256"].removeprefix("sha256:"),
        input_sha256=binding["native_sha256"].removeprefix("sha256:"),
        capture_era_native_sha256=case["native"]["sha256"],
        catalog_sha256=case["catalog"]["sha256"],
        tile=case["regions"][0],
        worker_wall_s=duration["wall_s"],
        worker_cpu_s=duration["cpu_s"],
        fit_envelope=duration,
        result=result,
    )


def run_chain(case_id, directory, library):
    prior = preflight(case_id, library)
    case = _load_case(case_id)
    started, start_cpu = perf_counter(), cpu_s()

    def finish(out, ident, deadline, detector):
        raw_envelope = stamp(started, start_cpu)
        assembly_wall, assembly_cpu = perf_counter(), cpu_s()
        raw = raw_robust.assemble_raw(out, ident, deadline, detector)
        path = out / "native.json"
        document = json.loads(path.read_bytes())
        length = capture_duration(document)
        if length <= 0 or raw["native_sha256"] != _sha(path):
            raise ValueError("fresh detector artifact has invalid capture authority")
        same_native = raw["native_sha256"] == prior["native_sha256"]
        binding = recording_to_v5.bind_request(case, path, out / "experiment.json")
        raw_assembly = stamp(assembly_wall, assembly_cpu)
        del document
        first = profile_fit(case, path, binding, out, "secant", started)
        chain = stamp(started, start_cpu)
        first.update(
            whole_chain=chain,
            worker_wall_s=chain["wall_s"],
            worker_cpu_s=chain["cpu_s"],
            raw_replayed_here=True,
            fit_wall_s=first["fit_envelope"]["wall_s"],
        )
        first["result"]["metrics"].update(
            capture_seconds=length, actual_wall_s_per_recorded_s=chain["wall_s"] / length
        )
        recording_to_v5.save(out / "secant-position.json", first)
        print(
            ident,
            "secant whole-chain",
            first["result"]["status"],
            round(chain["wall_s"], 2),
            flush=True,
        )
        if _sha(path) != raw["native_sha256"]:
            raise ValueError("detector factors changed before the stock fit")
        second = profile_fit(case, path, binding, out, "reference", started)
        second.update(raw_replayed_here=False, fit_wall_s=second["fit_envelope"]["wall_s"])
        recording_to_v5.save(out / "reference-position.json", second)
        stages = dict(
            id=ident,
            capture_seconds=length,
            delivery_span_s=raw["window_delivery_span_s"],
            same_factors_as_prior_whole_iq=same_native,
            prior_complete_iq=prior["acquisition"],
            raw_replay=raw,
            raw_read_and_detector_envelope=raw_envelope,
            detector_factor_assembly_and_binding=raw_assembly,
            end_to_end=chain,
            secant_fit=first["fit_envelope"],
            stock_fit=second["fit_envelope"],
            pair_wall_s=perf_counter() - started,
            peak_self_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
            peak_single_child_rss_kib=getrusage(RUSAGE_CHILDREN).ru_maxrss,
        )
        recording_to_v5.save(out / "stage-receipt.json", stages)
        print(
            ident,
            "stock from same factors",
            second["result"]["status"],
            round(second["worker_wall_s"], 2),
            flush=True,
        )
        return stages

    return recording_to_v5.run_recording(case_id, directory, (0, 1), CAP_S, library, finish=finish)


def publish(source, output):
    rows, stages = {key: [] for key in METHODS}, {}
    for case in CASES:
        root = source / case
        stage = json.loads((root / "stage-receipt.json").read_bytes())
        stages[case] = stage
        selected = [json.loads((root / f"{key}-position.json").read_bytes()) for key in METHODS]
        expected = stage["raw_replay"]["native_sha256"]
        if any(r["id"] != case or r["native_sha256"] != expected for r in selected):
            raise ValueError("paired position file does not bind the same freshly measured IQ")
        if (
            selected[0]["raw_replayed_here"] is not True
            or selected[1]["raw_replayed_here"] is not False
            or selected[0]["catalog_sha256"] != selected[1]["catalog_sha256"]
            or selected[0]["tile"] != selected[1]["tile"]
        ):
            raise ValueError("measured scope or paired causal archive changed")
        requests = []
        request_sha = {}
        for key in METHODS:
            request_path = root / key / "request.json"
            request = json.loads(request_path.read_bytes())
            request_sha[key] = _sha(request_path)
            request["job"].pop("output_root")
            requests.append(request)
        if requests[0] != requests[1]:
            raise ValueError("the compact solvers received different scientific requests")
        stage["paired_request_sha256"] = request_sha
        stage["common_science_request_sha256"] = sha256(encoded(requests[0])).hexdigest()
        for key, row in zip(METHODS, selected, strict=True):
            rows[key].append(row)
    files = {}
    for key, (_, name) in METHODS.items():
        data = gzip.compress(b"".join(encoded(row) + b"\n" for row in rows[key]), mtime=0)
        write(output / name, data)
        files[name] = sha256(data).hexdigest()
    save_json(output / "stage-receipts.json", stages)
    files["stage-receipts.json"] = _sha(output / "stage-receipts.json")
    save_json(
        output / "prediction-lock.json",
        dict(
            cases=CASES,
            files=files,
            solver_seal_sha256=_sha(SOURCE),
            published_measurement_worker_sha256=_sha(FIT_WORKER),
        ),
    )


def score(output):
    seal = json.loads((output / "prediction-lock.json").read_bytes())
    if any(_sha(output / name) != expected for name, expected in seal["files"].items()):
        raise ValueError("numerical or stage receipts changed after the lock")
    refs = {r["id"]: r for r in references("smoke", None)[1]}
    pair = {key: read_predictions(output / name) for key, (_, name) in METHODS.items()}
    scores = []
    reference_rows = {}
    for case in CASES:
        ref = refs[case]
        before, after = (pair[key][case]["result"] for key in ("reference", "secant"))
        reference_rows[case] = {role: ref["reference"][role] for role in ROLES}
        for arm in ARMS:
            stock, fit = before["arms"][arm], after["arms"][arm]
            scores.append(
                dict(
                    id=case,
                    arm=arm,
                    secant_status=after["status"],
                    stock_status=before["status"],
                    secant_km=distance_km(fit["latlon"], ref["truth"]),
                    stock_km=distance_km(stock["latlon"], ref["truth"]),
                    secant_conditional_rms_hz=fit.get("rf_rms_hz"),
                    stock_conditional_rms_hz=stock.get("rf_rms_hz"),
                    endpoint_shift_km=distance_km(fit["latlon"], stock["latlon"]),
                    **{role + "_km": ref["reference"][role][arm].get("error_km") for role in ROLES},
                )
            )
    csv_file(output / "scores.csv", scores)
    save_json(output / "capture-era-reference-positions.json", reference_rows)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    actions = cli.add_mutually_exclusive_group(required=True)
    actions.add_argument("--replay", type=Path)
    actions.add_argument("--publish", type=Path)
    actions.add_argument("--score", type=Path)
    cli.add_argument("--source", type=Path)
    cli.add_argument("--case", choices=CASES)
    cli.add_argument("--library", type=Path, default=NATIVE_LIBRARY)
    args = cli.parse_args()
    if args.replay is not None:
        if args.case is None or os.sched_getaffinity(0) != {0, 1}:
            cli.error("run one case on CPUs 0 and 1")
        run_chain(
            args.case, local_output(args.replay) / args.case, args.library.resolve(strict=True)
        )
    elif args.publish is not None:
        if args.source is None:
            cli.error("publication needs the paired case receipts")
        publish(args.source, local_output(args.publish))
    else:
        score(local_output(args.score))


if __name__ == "__main__":
    main()
