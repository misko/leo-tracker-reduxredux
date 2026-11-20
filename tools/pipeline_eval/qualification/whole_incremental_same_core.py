"""Counterbalance the three detector modes on a small authenticated matched host panel."""

import argparse
import json
import os
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns

from .full_v5_check import _from_native, _sha

ORDERS = (
    ("stock", "full_fifth", "incremental"),
    ("full_fifth", "incremental", "stock"),
    ("incremental", "stock", "full_fifth"),
    ("stock", "incremental", "full_fifth"),
    ("incremental", "full_fifth", "stock"),
    ("full_fifth", "stock", "incremental"),
)


def project(output):
    return [
        [p for i, c in enumerate(row["candidates"]) if (p := _from_native(i, c)) is not None]
        for row in output["rows"]
    ]


def trial(plan):
    import numpy as np

    from leo.analysis.starlink import native_short_window
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame

    from ..variants.center_union import DifferentialUnionCall
    from ..variants.differential_runtime_fft import FftScout
    from ..variants.incremental_rescue import IncrementalRescueCall, SingleLaneScout

    if not Path(native_short_window.__file__).is_relative_to(plan["producer"]):
        raise ValueError("paired timing must use the recording's actual installed producer")
    if list(os.sched_getaffinity(0)) != [plan["cpu"]]:
        raise ValueError("paired timing left its CPU")
    if any(_sha(Path(name)) != digest for name, digest in plan["sources"].items()):
        raise ValueError("paired timing source changed")
    for asset in plan["assets"].values():
        if _sha(Path(asset["path"])) != asset["sha256"]:
            raise ValueError("paired timing assets differ from the full services")
    cases = plan["fixtures"]
    edge = cases[0]["archive"][0]["edge"]
    paths = {role: item["path"] for role, item in plan["assets"].items()}
    configure = dict(sample_rate_hz=10_000_000, fractional_epoch=True)
    pair = [
        np.asarray(qin_edge_pilot_frame(10_000_000, edge, symbol_roll=roll), dtype="<c16")
        for roll in (0, CONTROL_SYMBOL_ROLL)
    ]
    rows = []
    with ExitStack() as opened:
        ports = {
            name: opened.enter_context(
                native_short_window.NativeShortWindow(paths[name], *pair, **configure)
            )
            for name in ("stock", "full_fifth", "incremental")
        }
        dual = opened.enter_context(FftScout(paths["dual_scout"], edge))
        one = opened.enter_context(SingleLaneScout(paths["one_scout"], edge))
        direct = ports["stock"].analyze
        full = DifferentialUnionCall(ports["full_fifth"], edge, scout=dual)
        inc = IncrementalRescueCall(ports["incremental"], edge, scout=one)
        modes = {"stock": direct, "full_fifth": full, "incremental": inc}
        for row in cases:
            samples = np.load(row["fixture"], allow_pickle=False)
            if sha256(samples.tobytes()).hexdigest() != row["iq_sha256"].removeprefix("sha256:"):
                raise ValueError("paired timing waveform differs from the authenticated fixture")
            digest = {
                name: fingerprint(direct(samples) if name == "stock" else modes[name](samples)[0])
                for name in modes
            }
            if project(direct(samples)) != [p["candidates"] for p in row["archive"]]:
                raise ValueError("paired timing stock does not reproduce archival factors")
            for index, order in enumerate(ORDERS):
                for name in order:
                    wall, cpu = perf_counter_ns(), process_time_ns()
                    result = modes[name](samples)
                    t_cpu, t_wall = process_time_ns() - cpu, perf_counter_ns() - wall
                    output = result if name == "stock" else result[0]
                    if fingerprint(output) != digest[name]:
                        raise ValueError("timing run changed the native scientific payload")
                    rows.append(
                        dict(
                            visit=row["visit"],
                            role=name,
                            repeat=index,
                            cpu_ns=t_cpu,
                            wall_ns=t_wall,
                            stock_positive_lanes=sum(
                                any(c["passed_fractional_margin_gate"] for c in p["candidates"])
                                for p in row["archive"]
                            ),
                            native_output_sha256=digest[name],
                        )
                    )
    print(json.dumps(rows, sort_keys=True))


def fingerprint(result):
    return sha256(json.dumps(result, sort_keys=True, allow_nan=False).encode()).hexdigest()


def launch(case, cpu, work):
    import subprocess

    from .. import whole_iq
    from ..__main__ import ROOT, save_json
    from . import whole_center_union as historical
    from . import whole_incremental_trial as release
    from .recording_to_v5 import ARCHIVE_PYTHON

    lock, active = release.configured(work)
    preflight = work / f"preflight-{case}"
    manifests = whole_iq.read(preflight / "fixtures.json")
    old = whole_iq.read(historical.REPORT / "candidate-lock-v2.json")["assets"]
    assets = dict(
        stock=dict(
            path=manifests["release"]["paths"]["stock"],
            sha256=manifests["release"]["sha256"]["stock"],
        ),
        full_fifth=old["candidate"],
        dual_scout=old["scout"],
        incremental=active["assets"]["detector"],
        one_scout=active["assets"]["scout"],
    )
    producer = manifests["producer"]
    plan = dict(
        cpu=cpu,
        case=case,
        producer=producer,
        orders=ORDERS,
        assets=assets,
        full_input_lock_sha256=_sha(work / "input-lock.json"),
        sources={str(Path(__file__)): _sha(Path(__file__))},
        fixtures=[
            dict(row, fixture=str(preflight / f"fixture-{i}.npy"))
            for i, row in enumerate(manifests["fixtures"])
        ],
    )
    if cpu not in lock["cases"][case]["cpus"]:
        raise ValueError("paired timing is outside the assigned recording cores")
    path = preflight / "same-core-plan.json"
    save_json(path, plan)
    path.chmod(0o644)
    with (preflight / "same-core.json").open("xb") as out:
        subprocess.run(
            [
                "timeout",
                "35s",
                "taskset",
                "-c",
                str(cpu),
                "sudo",
                "-n",
                "-u",
                "leo",
                "--",
                "env",
                f"PYTHONPATH={producer}:{ROOT}",
                "OPENBLAS_NUM_THREADS=1",
                "OMP_NUM_THREADS=1",
                "MKL_NUM_THREADS=1",
                str(ARCHIVE_PYTHON),
                "-B",
                "-m",
                "tools.pipeline_eval.qualification.whole_incremental_same_core",
                "worker",
                str(path),
            ],
            check=True,
            stdout=out,
            cwd=ROOT,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    cmd = parser.add_subparsers(dest="action", required=True)
    where = cmd.add_parser("run")
    where.add_argument("case")
    where.add_argument("cpu", type=int)
    where.add_argument("work", type=Path)
    cmd.add_parser("worker").add_argument("plan", type=Path)
    args = parser.parse_args()
    if args.action == "worker":
        trial(json.loads(args.plan.read_bytes()))
    else:
        launch(args.case, args.cpu, args.work)
