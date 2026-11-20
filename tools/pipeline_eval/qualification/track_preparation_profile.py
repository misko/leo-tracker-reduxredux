"""Profile installed compact-v5 preparation on authenticated complete GLRT factors."""

import cProfile
import json
import pstats
import runpy
import sys
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

PILOTS = ("DS29-0082", "DS29-0247")


def worker(root, request):
    entry = runpy.run_path(str(root / "__main__.py"))
    entry["activate"](root)
    from leo.application.localization_v3 import prepare_native_scan
    from tools.pipeline_eval.variants.direct_lifetime_kernels import read_native

    from leo.analysis import graph_tracklets
    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.operations.tle_archive import TleArchiveReader
    from tools.pipeline_eval.variants.v5_direct_cavity import verified_json

    native = read_native(dict(path=request["native"], sha256="sha256:" + request["native_sha256"]))
    cfg = TrackConfig(**verified_json(request["track_config"], request["config_sha256"])["config"])
    archive = TleArchiveReader(Path(request["archive"]))
    elapsed, lanes, graphs = perf_counter(), [], []
    base_graph = graph_tracklets._graph
    base_path = graph_tracklets._best_path

    def measure_graph(t, y, config):
        result = base_graph(t, y, config)
        graphs.append(
            dict(
                points=len(t),
                edges=len(result[0]),
                transitions=sum(len(a) * len(b) for a, b in zip(*result[-2:], strict=True)),
            )
        )
        return result

    def measure_path(t, y, topology, available, enabled, config):
        before = process_time()
        outcome = base_path(t, y, topology, available, enabled, config)
        lanes.append(
            dict(
                points=len(t),
                edges=len(topology[0]),
                path=len(outcome[0]),
                cpu_s=process_time() - before,
            )
        )
        return outcome

    profile = cProfile.Profile(timer=process_time)
    with (
        patch.object(graph_tracklets, "_graph", measure_graph),
        patch.object(graph_tracklets, "_best_path", measure_path),
        profile,
    ):
        prepared = prepare_native_scan(
            native,
            archive,
            cfg,
            screen_latitude_deg=request["screen_center"][0],
            screen_longitude_deg=request["screen_center"][1],
        )
    entry["verify_project_modules"](root)
    stats = pstats.Stats(profile)
    entries = sorted(stats.stats.items(), key=lambda kv: kv[1][3], reverse=True)
    return dict(
        id=request["id"],
        status=prepared["status"],
        cpu_s=stats.total_tt,
        wall_s=perf_counter() - elapsed,
        observations=len(prepared["tracks"]["observations"]),
        tracks=len(prepared["tracks"]["tracks"]),
        native_sha256=request["native_sha256"],
        graphs=graphs,
        path_calls=lanes,
        profile=[
            dict(
                file=str(Path(file).relative_to(root)) if Path(file).is_relative_to(root) else file,
                line=line,
                function=function,
                primitive_calls=cc,
                calls=nc,
                self_cpu_s=tt,
                cumulative_cpu_s=ct,
            )
            for (file, line, function), (cc, nc, tt, ct, _) in entries[:150]
        ],
    )


def run(destination):
    from concurrent.futures import ThreadPoolExecutor
    from uuid import uuid4

    from .. import iq_service
    from ..__main__ import THREAD_ENV, local_output, save_json
    from ..original_receiver import CALIBRATION, receiver_assets
    from . import capture_whole, sequential_fix_trial
    from .full_v5_check import _sha

    destination = local_output(destination)
    destination.mkdir()
    receiver_assets(CALIBRATION)

    def emit(job):
        ident, cpu = job
        request = sequential_fix_trial.prepare_recording(ident)
        out = destination / ident
        out.mkdir()
        path = out / "request.json"
        save_json(path, request)
        save_json(out / "plan.json", dict(cpus=[cpu], limit_s=120, request_sha256=_sha(path)))
        unit = "leo-iq-bench-" + uuid4().hex[:12]
        command = capture_whole.service(
            unit,
            120,
            [
                f"--setenv=TMPDIR={out}",
                *(f"--setenv={k}={v}" for k, v in THREAD_ENV.items()),
                "taskset",
                "-c",
                str(cpu),
                sys.executable,
                "-B",
                "-m",
                __spec__.name,
                "worker",
                str(out),
            ],
        )
        result = iq_service.run(out, command, unit, timeout=140)
        if not iq_service.succeeded(result):
            raise RuntimeError(f"installed preparation profile did not finish for {ident}")

    with patch.object(iq_service, "MODULE", __spec__.name), ThreadPoolExecutor(2) as pool:
        list(pool.map(emit, zip(PILOTS, (14, 15), strict=True)))


def profile_folder(out):
    import subprocess

    from .. import whole_iq
    from ..__main__ import save_json
    from ..original_receiver import CALIBRATION, receiver_assets
    from .whole_memory_chain_worker import memory

    plan = whole_iq.read(out / "plan.json")
    request = whole_iq.checked(out / "request.json", plan["request_sha256"])
    receiver_assets(CALIBRATION)
    result = subprocess.run(
        [sys.executable, "-IB", __file__, "isolated", str(CALIBRATION), str(request)],
        stdout=subprocess.PIPE,
        check=True,
    )
    save_json(out / "profile.json", dict(json.loads(result.stdout), resources=memory()))


if __name__ == "__main__":
    if sys.argv[1] == "isolated":
        data = json.loads(Path(sys.argv[3]).read_bytes())
        print(json.dumps(worker(Path(sys.argv[2]), data)))
    elif sys.argv[1] == "worker":
        profile_folder(Path(sys.argv[2]))
    else:
        run(Path(sys.argv[1]))
