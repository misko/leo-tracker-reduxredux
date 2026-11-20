"""Measure catalogue-axis propagation batches with matched frozen v5 workers."""

import argparse
import gzip
import json
import os
import sys
from contextlib import ExitStack
from importlib import import_module
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from time import perf_counter, process_time
from unittest.mock import patch

from tools.pipeline_eval.__main__ import (
    DEFAULT_OUT,
    ROOT,
    encoded,
    local_output,
    public_cases,
    references,
    save_json,
    write,
)
from tools.pipeline_eval.qualification.batched_salvage_eval import observed
from tools.pipeline_eval.qualification.compact_finish_eval import verify_adapter
from tools.pipeline_eval.qualification.v5_postfit import sha256
from tools.pipeline_eval.scoring import ARMS, distance_km
from tools.pipeline_eval.variants import (
    compact_finish,
    orbit_projector,
    v5_catalogue_memory,
    v5_lean,
)

METHOD = "v5_catalogue_memory"
STOCK = "compact_finish"
RETAINED_BANK = "retained-bank"
RUNS = {
    "DS26-0036": ("ds26-common127", 20, (METHOD, STOCK)),
    "DS29-0082": ("roof16", 21, (STOCK, METHOD)),
}
STAGES = {
    "leo.analysis.localization_v3.conservative_recovery": ("conservative_recovery",),
    "leo.analysis.localization_v3.residual_screen": ("screen_candidates", "ecef_states"),
    "leo.analysis.localization_v3.reassociation_catalogue": ("ecef_states", "audit"),
    "leo.analysis.localization_v3.reassociation_admission": ("prepare_catalogue", "screen"),
}
BASELINE = ROOT / "reports/2026_11_19_receiver_streaming/finish"


def worker(request, result, library, log, method):
    with Path(log).open("x") as events, ExitStack() as stack:
        usage = None
        if method != STOCK:
            usage = stack.enter_context(
                v5_catalogue_memory.catalogue_batches(retain=method == RETAINED_BANK)
            )
        for module, names in STAGES.items():
            owner = import_module(module)
            for name in names:
                operation = getattr(owner, name)
                qualified = f"{module}.{name}"
                if name == "ecef_states":
                    operation = observed_states(qualified, operation, events)
                else:
                    operation = observed(qualified, operation, events)
                stack.enter_context(patch.object(owner, name, operation))
        run = observed("numerical_worker", compact_finish.worker, events)
        run(request, result, library)
        if usage is not None:
            print(
                json.dumps(dict(name="residual_bank_ownership", **usage)), file=events, flush=True
            )


def observed_states(name, operation, events):
    def run(catalogue, origin, times):
        instrumented = observed(
            name,
            operation,
            events,
            satellites=len(catalogue),
            knots=len(times),
            ecef_output_bytes=2 * len(catalogue) * len(times) * 3 * 8,
        )
        return instrumented(catalogue, origin, times)

    return run


def cpu_elapsed():
    children = getrusage(RUSAGE_CHILDREN)
    return process_time() + children.ru_utime + children.ru_stime


def assert_frozen(case, result):
    ident = case["id"]
    prior = json.loads((BASELINE / f"adapter/{ident}.json").read_bytes())
    verify_adapter(prior, result)
    original = json.loads((BASELINE / f"{ident}-v5_lean.json").read_bytes())
    if original["input_sha256"] != result["input_sha256"]:
        raise ValueError("Frozen original v5 and catalogue variant used different inputs")
    for arm in ARMS:
        expected = original["result"]
        actual = result["result"]
        for field in ("conditional_rms_hz", "frequency_score", "associated_observations"):
            key = f"{arm}_{field}"
            if actual["metrics"][key] != expected["metrics"][key]:
                raise ValueError(f"{ident} differs from frozen v5 on {key}")
        if actual["arms"][arm]["latlon"] != expected["arms"][arm]["latlon"]:
            raise ValueError(f"{ident} differs from frozen v5 on {arm} position")


def pair(ident, output, *, retain):
    panel, cpu, order = RUNS[ident]
    if os.sched_getaffinity(0) != {cpu}:
        raise ValueError(f"Both measurements for {ident} must run on CPU {cpu}")
    source, refs = references(panel, [ident])
    (case,) = public_cases(source, refs, DEFAULT_OUT / "inputs")
    output = local_output(output)
    for method in (METHOD,) if retain else order:
        run = output / ident / method
        run.mkdir(parents=True, exist_ok=False)
        library = run / "orbit_projector.so"
        events = run / "stages.jsonl"
        began, started_cpu = perf_counter(), cpu_elapsed()
        orbit_projector.compile_kernel(library)
        mode = RETAINED_BANK if retain else method
        result = v5_lean.run_bound_worker(
            case, run / "worker", Path(__file__), worker_args=(str(library), str(events), mode)
        )
        path = Path((v5_catalogue_memory if method == METHOD else compact_finish).__file__)
        record = dict(
            id=ident,
            method=method,
            mode=mode,
            cpu=cpu,
            input_sha256=sha256(encoded(case))[7:],
            implementation_sha256=sha256(path.read_bytes())[7:],
            result=result,
            worker_wall_s=perf_counter() - began,
            worker_cpu_s=cpu_elapsed() - started_cpu,
        )
        save_json(run / "result.json", record)
        assert_frozen(case, record)
        print(ident, method, round(record["worker_wall_s"], 2), flush=True)


def package(runs, retained, output):
    output = local_output(output)
    predictions = {STOCK: [], METHOD: []}
    comparisons = []
    stage_digests = {}
    for ident, (panel, cpu, _) in RUNS.items():
        _, (ref,) = references(panel, [ident])
        row = dict(id=ident, cpu=cpu, methods={})
        for method in predictions:
            source = (retained if method == METHOD else runs) / ident / method
            record = json.loads((source / "result.json").read_bytes())
            assert_frozen({"id": ident}, record)
            predictions[method].append(record)
            raw = (source / "stages.jsonl").read_bytes()
            stages = [json.loads(line) for line in raw.splitlines()]
            (whole,) = [s for s in stages if s["name"] == "numerical_worker"]
            if method == METHOD:
                (ownership,) = [s for s in stages if s["name"] == "residual_bank_ownership"]
                if ownership["retained"] != 1 or ownership["copied"] != 0:
                    raise ValueError(f"{ident} did not use exclusive residual bank ownership")
            name = f"{ident}-{method}-stages.jsonl.gz"
            compressed = gzip.compress(raw, mtime=0)
            write(output / name, compressed)
            stage_digests[name] = sha256(compressed)
            row["methods"][method] = dict(
                wall_s=record["worker_wall_s"],
                cpu_s=record["worker_cpu_s"],
                worker_peak_kib=whole["after_peak_kib"],
                geographic_error_km={
                    a: distance_km(ref["truth"], record["result"]["arms"][a]["latlon"])
                    for a in ARMS
                },
                conditional_rms_hz={
                    a: record["result"]["metrics"][f"{a}_conditional_rms_hz"] for a in ARMS
                },
            )
        row["input_sha256"] = record["input_sha256"]
        comparisons.append(row)
        pilot = runs / ident / METHOD / "stages.jsonl"
        filename = f"{ident}-propagation-only-stages.jsonl.gz"
        compressed = gzip.compress(pilot.read_bytes(), mtime=0)
        write(output / filename, compressed)
        stage_digests[filename] = sha256(compressed)
    artifacts = {}
    for role, method, filename in (
        ("control", STOCK, "stock-positions.jsonl.gz"),
        ("candidate", METHOD, "positions.jsonl.gz"),
    ):
        raw = gzip.compress(b"".join(encoded(r) + b"\n" for r in predictions[method]), mtime=0)
        write(output / filename, raw)
        artifacts[role] = dict(method=method, positions=filename, position_sha256=sha256(raw)[7:])
    save_json(
        output / "receipt.json",
        dict(
            method=METHOD,
            control=STOCK,
            frozen_source=v5_lean.SOURCE_SHA256,
            satellites_per_batch=v5_catalogue_memory.SATELLITES_PER_BATCH,
            cases=list(RUNS),
            comparisons=comparisons,
            runs=artifacts,
            stage_archives=stage_digests,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=RUNS)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--retained", type=Path)
    parser.add_argument("--retain", action="store_true")
    args = parser.parse_args()
    if args.case:
        pair(args.case, args.out, retain=args.retain)
    elif args.package and args.retained:
        package(args.package, args.retained, args.out)
    else:
        parser.error("provide a recording or paired run directory")


if __name__ == "__main__":
    if len(sys.argv) == 6 and sys.argv[-1] in (STOCK, METHOD, RETAINED_BANK):
        worker(*sys.argv[1:])
    else:
        main()
