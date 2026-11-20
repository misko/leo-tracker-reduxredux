"""Re-fit only authenticated, emitted native packets after actual FIFO drops."""

import argparse
import gzip
import json
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from . import arrival_queue as pace
from . import arrival_queue_cost as costs
from . import bracketed_position as fit
from .arrival_queue_results import terminal
from .bracketed_position_results import service_result
from .full_v5_check import _sha
from .phase_support_results import pack
from .whole_pressure_trial import rows_from

METHODS = {m: f"arrival_queue_{m}" for m in pace.MODES}


def subtract(document, dropped, trace_sha):
    scheduled = document["source"]["probes"]
    if not dropped or not dropped <= {p["visit_index"] for p in scheduled}:
        raise ValueError("drop set must be valid recorded detector opportunities")
    kept = [p for p in scheduled if p["visit_index"] not in dropped]
    if len(scheduled) - len(kept) != 2 * len(dropped):
        raise ValueError("a FIFO drop must remove both receiver rows of its physical visit")
    identity = pace.recording_to_v5.digest(
        [
            "delivery-queue-retained-native-v1",
            document["source"]["analysis_manifest_sha256"],
            trace_sha,
            sorted(dropped),
        ]
    )
    return dict(
        document,
        source=dict(document["source"], probes=kept, analysis_manifest_sha256=identity),
        provenance=dict(
            document["provenance"],
            run_id="replay-" + identity[7:39],
            processed_windows=len(kept) // 2,
            scope="Byte-verified native visits retained after a real FIFO replay",
        ),
    )


def run(work, report, mode):
    lock = pace.plan(work, report)
    path = pace.PARENT / "prediction-lock.json"
    prior = whole_iq.read(whole_iq.checked(path, lock["parent_prediction_sha256"]))

    def parent(name):
        return whole_iq.checked(pace.PARENT / name, prior["files"][name])

    release = whole_iq.read(parent("source-lock.json"))
    fit.check_release(release)
    archived = {(r["id"], r["method"]): r for r in rows_from(parent("positions.jsonl.gz"))}
    methods = dict(
        control=pace.whole_center_union.BASELINE, candidate=pace.whole_center_union.METHOD
    )
    inputs = {}
    output = report / f"positions-{mode}.jsonl.gz"
    for ident, spec in lock["cases"].items():
        reference = spec["modes"][mode]
        events = pace.readgz(whole_iq.checked(report / reference["events"], reference["sha256"]))
        attempt = work / ident / mode
        trace, witness, service, complete = terminal(attempt, events)
        drops = [r for r in trace if r["outcome"] == "queue_drop"]
        control = archived[ident, methods[mode]]
        cpu = costs.CPUS[ident]
        out = work / ident / ("position-" + mode)
        out.mkdir(exist_ok=False)
        if complete and drops:
            native = out / "native.json"
            blob = gzip.decompress(parent(f"native/{mode}/{ident}.json.gz").read_bytes())
            if sha256(blob).hexdigest() != control["native_sha256"]:
                raise ValueError("archive did not bind the original position")
            capture = subtract(
                json.loads(blob), {r["visit"] for r in drops}, witness["output_sha256"]
            )
            write(native, (pace.recording_to_v5.encoded(capture) + "\n").encode())
            case, original = whole_iq.binding(ident)
            job = original["job"]
            save_json(
                out / "request.json",
                dict(
                    native=str(native),
                    native_sha256=_sha(native),
                    session=case["session_id"],
                    config=job["track_config"],
                    archive=job["tle_root"],
                    tile=job["search_center"],
                    screen=job["screen_center"],
                    install=release["receiver"],
                    cpu=cpu,
                ),
            )
        inputs[ident] = dict(
            out=str(out),
            cpu=cpu,
            complete=complete,
            dropped=drops,
            paced_log_sha256=service["log_sha256"],
            trace_sha256=witness["output_sha256"] if witness else None,
            request_sha256=_sha(out / "request.json") if (out / "request.json").exists() else None,
            archive_native_sha256=control["native_sha256"],
        )
    source = report / f"position-{mode}-input-lock.json"
    save_json(source, dict(cases=inputs, program_sha256=_sha(Path(__file__))))

    def evaluate(ident):
        item = inputs[ident]
        control = archived[ident, methods[mode]]
        if item["request_sha256"]:
            out = Path(item["out"])
            request = whole_iq.read(whole_iq.checked(out / "request.json", item["request_sha256"]))
            native = whole_iq.checked(Path(request["native"]), request["native_sha256"])
            fit.launch_case(out, item["cpu"])
            result, metrics = service_result(out, item["cpu"])
            origin, native_sha = "fresh paced-retained factor fit", _sha(native)
        else:
            result, metrics = control["result"], {}
            origin = (
                "exact archived same-input position"
                if item["complete"]
                else "paced attempt incomplete"
            )
            native_sha = control["native_sha256"] if item["complete"] else None
            if not item["complete"]:
                result = dict(
                    status="unavailable",
                    reason=origin,
                    boundary=origin,
                    metrics={},
                    arms={a: dict(latlon=None) for a in ("c0", "fitted_c")},
                )
        return dict(
            control,
            method=METHODS[mode],
            result=result,
            native_sha256=native_sha,
            origin=origin,
            resources=metrics,
            dropped=len(item["dropped"]),
            paired_paced_native_sha256=control["native_sha256"],
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(evaluate, pace.CPUS))
    pack(output, records)
    save_json(
        report / f"positions-{mode}-lock.json",
        dict(
            cases=list(pace.CPUS),
            files={p.name: _sha(p) for p in (source, output)},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=pace.MODES)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--out", type=local_output, default=pace.REPORT)
    args = parser.parse_args()
    run(args.work, args.out, args.mode)
