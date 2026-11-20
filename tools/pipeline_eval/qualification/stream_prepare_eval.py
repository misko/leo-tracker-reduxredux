"""Run paired native preparation and complete compact v5 position measurements."""

import argparse
import gzip
import json
import os
import sys
from contextlib import ExitStack
from functools import wraps
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import perf_counter, process_time
from unittest.mock import patch

from tools.pipeline_eval.__main__ import (
    DEFAULT_OUT,
    encoded,
    local_output,
    public_cases,
    references,
    save_json,
    write,
)
from tools.pipeline_eval.qualification.catalogue_memory_eval import assert_frozen, cpu_elapsed
from tools.pipeline_eval.qualification.compact_finish_eval import verify_adapter
from tools.pipeline_eval.qualification.v5_postfit import sha256
from tools.pipeline_eval.scoring import ARMS, distance_km
from tools.pipeline_eval.variants import compact_finish, orbit_projector, v5_lean, v5_stream_prepare

METHOD = "v5_stream_prepare"
STOCK = "compact_finish"
RUNS = {
    "DS26-0036": ("ds26-common127", 20, (METHOD, STOCK)),
    "DS29-0082": ("roof16", 21, (STOCK, METHOD)),
}


def rss():
    resident = int(Path("/proc/self/statm").read_text().split()[1])
    return resident * os.sysconf("SC_PAGE_SIZE") // 1024


def observed(name, operation, log, summarize=None):
    @wraps(operation)
    def run(*args, **kwargs):
        current, peak = rss(), getrusage(RUSAGE_SELF).ru_maxrss
        start, cpu = perf_counter(), process_time()
        value = operation(*args, **kwargs)
        record = dict(
            name=name,
            wall_s=perf_counter() - start,
            cpu_s=process_time() - cpu,
            resident_before_kib=current,
            resident_after_kib=rss(),
            before_peak_kib=peak,
            after_peak_kib=getrusage(RUSAGE_SELF).ru_maxrss,
        )
        if summarize is not None:
            record.update(summarize(value, *args, **kwargs))
        print(json.dumps(record, allow_nan=False), file=log, flush=True)
        return value

    return run


def graph_receipt(result, document, config):
    data = json.dumps(result, sort_keys=True, allow_nan=False, default=lambda value: value.tolist())
    return dict(
        graph_input_sha256=sha256(data.encode())[7:],
        observations=len(result["observations"]),
        tracks=len(result["tracks"]),
        raw_document_live=bool(document),
    )


def worker(request, result, library, log_path, method):
    from leo.application import localization_v3
    from leo.operations import localization_v3_job

    native = v5_lean._read(request)["job"]["native_input"]
    with Path(log_path).open("x") as log, ExitStack() as stack:
        if method == METHOD:
            stack.enter_context(v5_stream_prepare.stream_preparation(native))
        read_bound = localization_v3_job.read_bound
        native_read = observed("native_read", read_bound, log)

        def read(record):
            return (native_read if record == native else read_bound)(record)

        stack.enter_context(patch.object(localization_v3_job, "read_bound", read))
        for name, stage, summary in (
            ("prepare_tracks", "prepare_tracks", graph_receipt),
            ("prepare_native_scan", "prepare_native_scan", None),
        ):
            measure = observed(stage, getattr(localization_v3, name), log, summary)
            stack.enter_context(patch.object(localization_v3, name, measure))
        observed("worker", compact_finish.worker, log)(request, result, library)


def replay(ident, output):
    panel, cpu, order = RUNS[ident]
    if os.sched_getaffinity(0) != {cpu}:
        raise ValueError(f"Both replays of {ident} must use CPU {cpu}")
    source, refs = references(panel, [ident])
    (case,) = public_cases(source, refs, DEFAULT_OUT / "inputs")
    for method in order:
        run = local_output(output) / ident / method
        run.mkdir(parents=True, exist_ok=False)
        library = run / "orbit_projector.so"
        log = run / "stages.jsonl"
        start, cpu_start = perf_counter(), cpu_elapsed()
        orbit_projector.compile_kernel(library)
        result = v5_lean.run_bound_worker(
            case, run / "worker", Path(__file__), worker_args=(str(library), str(log), method)
        )
        wall, cpu_time = perf_counter() - start, cpu_elapsed() - cpu_start
        variant = v5_stream_prepare if method == METHOD else compact_finish
        record = dict(
            id=ident,
            method=method,
            cpu=cpu,
            result=result,
            input_sha256=sha256(encoded(case))[7:],
            implementation_sha256=sha256(Path(variant.__file__).read_bytes())[7:],
            worker_wall_s=wall,
            worker_cpu_s=cpu_time,
        )
        save_json(run / "result.json", record)
        assert_frozen(case, record)
        print(ident, method, round(wall, 2), round(cpu_time, 2), flush=True)


def package(runs, output):
    output = local_output(output)
    positions = {STOCK: [], METHOD: []}
    comparisons = []
    traces = {}
    for ident, (panel, cpu, _) in RUNS.items():
        _, (ref,) = references(panel, [ident])
        methods, receipts = {}, {}
        for method in positions:
            run = runs / ident / method
            item = json.loads((run / "result.json").read_bytes())
            assert_frozen({"id": ident}, item)
            receipts[method] = item
            raw = (run / "stages.jsonl").read_bytes()
            measurements = {r["name"]: r for r in map(json.loads, raw.splitlines())}
            filename = f"{ident}-{method}-stages.jsonl.gz"
            compressed = gzip.compress(raw, mtime=0)
            write(output / filename, compressed)
            traces[filename] = sha256(compressed)[7:]
            methods[method] = dict(
                stages=measurements,
                worker_cpu_s=item["worker_cpu_s"],
                worker_wall_s=item["worker_wall_s"],
                geographic_error_km={
                    arm: distance_km(ref["truth"], item["result"]["arms"][arm]["latlon"])
                    for arm in ARMS
                },
                conditional_rms_hz={
                    arm: item["result"]["metrics"][f"{arm}_conditional_rms_hz"] for arm in ARMS
                },
            )
            positions[method].append(item)
        verify_adapter(receipts[STOCK], receipts[METHOD])
        a, b = (methods[k]["stages"]["prepare_tracks"] for k in (STOCK, METHOD))
        if (
            a["graph_input_sha256"] != b["graph_input_sha256"]
            or not a["raw_document_live"]
            or b["raw_document_live"]
        ):
            raise ValueError(f"{ident} graph inputs or private input ownership differ")
        comparisons.append(
            dict(id=ident, cpu=cpu, input_sha256=item["input_sha256"], methods=methods)
        )
    archives = {}
    for role, method, filename in (
        ("control", STOCK, "stock-positions.jsonl.gz"),
        ("candidate", METHOD, "positions.jsonl.gz"),
    ):
        raw = gzip.compress(b"".join(encoded(r) + b"\n" for r in positions[method]), mtime=0)
        write(output / filename, raw)
        archives[role] = dict(method=method, positions=filename, position_sha256=sha256(raw)[7:])
    save_json(
        output / "receipt.json",
        dict(
            cases=list(RUNS),
            runs=archives,
            comparisons=comparisons,
            stage_archives=traces,
            method=METHOD,
            control=STOCK,
            frozen_source=v5_lean.SOURCE_SHA256,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=RUNS)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--package", type=Path)
    args = parser.parse_args()
    if args.case:
        replay(args.case, args.out)
    elif args.package:
        package(args.package, args.out)
    else:
        parser.error("provide a recording or paired run directory")


if __name__ == "__main__":
    if len(sys.argv) == 6 and sys.argv[-1] in (METHOD, STOCK):
        worker(*sys.argv[1:])
    else:
        main()
