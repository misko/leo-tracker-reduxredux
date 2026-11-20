"""Paired complete compact-v5 trials with a source-verified nomination overlay."""

import argparse
import hashlib
import inspect
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from resource import RUSAGE_CHILDREN, RUSAGE_SELF, getrusage
from time import perf_counter, process_time, time_ns
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.__main__ import ROOT, local_output, save_json
from tools.pipeline_eval.qualification.broad_search_budget import _case, frozen_inputs
from tools.pipeline_eval.qualification.pruned_finish_eval import execution_binding
from tools.pipeline_eval.scoring import ARMS, validate_result
from tools.pipeline_eval.variants import cavity_covariance as low
from tools.pipeline_eval.variants import compact_finish, orbit_projector, v5_core, v5_lean

REPORT = ROOT / "reports/2026_11_19_receiver_screening/recovery/cavity-covariance"
STOCK = "compact_finish"
METHODS = (low.METHOD, STOCK)
LANES = {"DS26-0036": 7, "DS29-0082": 17}
FROZEN = {
    "family_cavity": "7a20ac84d4c245df95481d10425def01642cbf4d3f45f1f32b9188a78007b3ae",
    "cavity_prediction": "be422d23c3a547dcb964987155276440dee82babe32a21afd84570c13a0e3e19",
}
REPLACED = """    covariance = (
        np.diag(noise**2)
        + radio @ cov[:radio_width, :radio_width] @ radio.T
        + 300.0**2 * (groups[:, None] == groups[None, :])
    )"""
REPLACEMENT = (
    """    covariance = BaseCovariance(noise, radio, cov[:radio_width, :radio_width], groups)"""
)
STUDY_S = 510
LEG_S = 260


def sha(value):
    return hashlib.sha256(value).hexdigest()


def frozen_hashes():
    folder = v5_lean.SOURCE / "leo/analysis/localization_v3"
    result = {name: sha((folder / f"{name}.py").read_bytes()) for name in FROZEN}
    if result != FROZEN:
        raise ValueError("frozen cavity sources differ from the reviewed overlay")
    return result


def _overlay(function):
    source = inspect.getsource(function)
    if source.count(REPLACED) != 1:
        raise ValueError("expected one exact frozen covariance construction")
    namespace = dict(function.__globals__, BaseCovariance=low.BaseCovariance)
    path = inspect.getsourcefile(function)
    exec(compile(source.replace(REPLACED, REPLACEMENT), path, "exec"), namespace)
    return namespace[function.__name__]


def _stamp():
    rss = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in ("VmRSS", "VmHWM"):
            rss[key] = int(value.split()[0])
    return dict(wall_s=perf_counter(), cpu_s=process_time(), rss=rss)


def _stage(start):
    end = _stamp()
    return dict(
        wall_s=end["wall_s"] - start["wall_s"],
        cpu_s=end["cpu_s"] - start["cpu_s"],
        rss_before_kib=start["rss"],
        rss_after_kib=end["rss"],
    )


def _array_hash(value, dtype):
    return sha(np.asarray(value, dtype=dtype).tobytes())


def _nominations(result):
    families = []
    for row in result.get("families", []):
        candidates = []
        for c in row["candidates"]:
            residual = c["residual_hz"]
            stop = 0
            source = []
            for group in row["members"]:
                start, stop = stop, stop + group["points"]
                source.append(
                    dict(
                        component=group["component"],
                        points=group["points"],
                        rms_hz=float(np.sqrt(np.mean(residual[start:stop] ** 2))),
                        residual_sha256=_array_hash(residual[start:stop], "<f8"),
                    )
                )
            if stop != len(residual):
                raise ValueError("restored proposal residual differs from its native source roster")
            candidates.append(
                dict(
                    index=c["candidate_index"],
                    norad=c["norad"],
                    aliases=np.asarray(c["aliases"]).tolist(),
                    qualified=c["qualified"],
                    score=c["score"],
                    rms_hz=c["conditional_RMS_hz"],
                    phase_s=c["phase_s"],
                    source=source,
                )
            )
        families.append(
            dict(
                original=row["original_norad"],
                candidates=candidates,
                best=None if row["best"] is None else row["best"]["norad"],
                predictive_gain=row["predictive_gain"],
            )
        )
    return dict(status=result["status"], error=result.get("error"), families=families)


def worker(request, output, library, method):
    from leo.analysis.localization_v3 import cavity_prediction, family_cavity

    frozen_hashes()
    for module in (family_cavity, cavity_prediction):
        if sha(Path(module.__file__).read_bytes()) != FROZEN[module.__name__.rsplit(".", 1)[-1]]:
            raise ValueError("the loaded cavity module is not the authenticated source")
    candidate = method == low.METHOD
    stock_score = cavity_prediction.coarse_phase_scores
    build = _overlay(family_cavity.family_data) if candidate else family_cavity.family_data
    nominate = family_cavity.nominate_families
    restore = family_cavity.cavity_policy
    telemetry = dict(coarse=[], family_data=[], mode_space=[])

    def family(*args):
        start = _stamp()
        data = build(*args)
        telemetry["family_data"].append(_stage(start))
        return data

    def scores(*args):
        start = _stamp()
        result = (
            low.coarse_phase_scores(*args, stock=stock_score, telemetry=telemetry["mode_space"])
            if candidate
            else stock_score(*args)
        )
        entry = _stage(start)
        entry.update(
            order_sha256=_array_hash(np.argsort(result["score"]), "<i8"),
            aliases_sha256=_array_hash(result["aliases"], "<i8"),
        )
        telemetry["coarse"].append(entry)
        return result

    def nominations(*args):
        start = _stamp()
        result = nominate(*args)
        telemetry["nomination_stage"] = _stage(start)
        telemetry["nominations"] = _nominations(result)
        return result

    def restored(*args):
        start = _stamp()
        result = restore(*args)
        telemetry["restored_stage"] = _stage(start)
        telemetry["restored"] = dict(
            status=result["status"],
            accepted=result.get("accepted"),
            chosen=None if result.get("selected") is None else result["selected"]["replacements"],
            trials=[
                dict(
                    replacements=r["replacements"],
                    valid=r["paired_valid"],
                    arm_scores={a: v["corrected_selection_loss"] for a, v in r["arms"].items()},
                )
                for r in result.get("trials", [])
            ],
        )
        return result

    with (
        patch.object(family_cavity, "family_data", family),
        patch.object(family_cavity, "coarse_phase_scores", scores),
        patch.object(family_cavity, "nominate_families", nominations),
        patch.object(family_cavity, "cavity_policy", restored),
    ):
        compact_finish.worker(request, output, library)
    result = json.loads(Path(output).read_bytes())
    result["boundary"] = low.BOUNDARY if candidate else compact_finish.BOUNDARY
    result["metrics"]["cavity_covariance_observer"] = telemetry
    result["metrics"]["worker_peak_rss_kib"] = getrusage(RUSAGE_SELF).ru_maxrss
    save_json(Path(output), result)


def _read(path):
    return json.loads(path.read_bytes())


def _cpu():
    stats = getrusage(RUSAGE_CHILDREN)
    return stats.ru_utime + stats.ru_stime


def source_tokens():
    paths = [Path(m.__file__) for m in (low, compact_finish, orbit_projector, v5_core, v5_lean)]
    paths += [Path(__file__), orbit_projector.KERNEL, REPORT / "PROTOCOL.md"]
    return {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in paths}


def one(ident, lane, work, plan):
    if plan["source"] != source_tokens() or os.sched_getaffinity(0) != {lane}:
        raise ValueError("the worker source or pinned core differs from the sealed request")
    item = frozen_inputs()[ident]
    case = _case(item)
    bound = execution_binding(item, case)
    if bound != plan["bindings"][ident]:
        raise ValueError("native inputs differ from the sealed request")
    for method in plan["order"][ident]:
        run = work / ident / method
        run.mkdir(parents=True, exist_ok=False)
        library = run / "orbit_projector.so"
        wall, used = perf_counter(), _cpu()
        remaining = (plan["deadline_ns"] - time_ns()) // 10**9
        if remaining > 5:
            orbit_projector.compile_kernel(library)
            with patch.object(v5_lean, "TIMEOUT_S", min(LEG_S, remaining - 3)):
                result = v5_lean.run_bound_worker(
                    case, run, Path(__file__), worker_args=(str(library), method)
                )
        else:
            result = v5_lean._no_fix("common deadline before launch", status="missing")
        if "exceeded its " in (result.get("reason") or ""):
            result["status"] = "timed_out"
        if result["status"] != "ok":
            result.setdefault("arms", {arm: {"latlon": None} for arm in ARMS})
        validate_result(result)
        record = dict(
            id=ident,
            method=method,
            cpu=lane,
            result=result,
            input_sha256=bound["input_sha256"],
            native_sha256=item["native"]["sha256"],
            catalog_sha256=item["catalog"]["sha256"],
            worker_wall_s=perf_counter() - wall,
            worker_cpu_s=_cpu() - used,
        )
        save_json(work / f"{ident}-{method}.json", record)
        print(ident, method, result["status"], round(record["worker_wall_s"], 2), flush=True)


def run(work):
    work = local_output(work)
    work.mkdir(parents=True, exist_ok=False)
    initial = time_ns()
    frozen_hashes()
    inputs = frozen_inputs()
    optional = {
        i: min(
            (k for k in inputs if k.startswith(i[:4]) and k not in LANES),
            key=lambda k: sha(("cavity-covariance-v1:" + k).encode()),
        )
        for i in LANES
    }
    cases = [*LANES, *optional.values()]
    order = {i: METHODS if (j % 2 == 0) else METHODS[::-1] for j, i in enumerate(cases)}
    plan = dict(
        primary=list(LANES),
        optional=optional,
        order=order,
        source=source_tokens(),
        frozen=FROZEN,
        deadline_ns=initial + STUDY_S * 10**9,
        bindings={i: execution_binding(inputs[i], _case(inputs[i])) for i in cases},
    )
    save_json(work / "plan.json", plan)
    save_json(REPORT / "plan.json", plan)

    def lane(ident, cpu):
        def launch(case):
            subprocess.run(
                [
                    "taskset",
                    "-c",
                    str(cpu),
                    sys.executable,
                    "-m",
                    "tools.pipeline_eval.qualification.cavity_covariance",
                    "one",
                    case,
                    str(cpu),
                    str(work),
                ],
                check=True,
            )

        launch(ident)
        if plan["deadline_ns"] - time_ns() > 210 * 10**9:
            launch(optional[ident])

    with ThreadPoolExecutor(2) as pool:
        jobs = [pool.submit(lane, case, cpu) for case, cpu in LANES.items()]
        for job in jobs:
            job.result()


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1].endswith(".json"):
        worker(*sys.argv[1:])
    elif len(sys.argv) == 5 and sys.argv[1] == "one":
        ident, cpu, work = sys.argv[2:]
        one(ident, int(cpu), Path(work), _read(Path(work) / "plan.json"))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--work", required=True, type=Path)
        run(parser.parse_args().work)
