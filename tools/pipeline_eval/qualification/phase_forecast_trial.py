"""Lock and run one signed-mean native receiver after catalogue-only validation."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, read_predictions, save_json
from ..scoring import ARMS, validate_result
from ..variants import phase_forecast as law
from . import native_joint_full as panel
from . import phase_forecast_catalogue as proxy
from . import phase_forecast_history as history
from .armijo_finish_results import pack
from .phase_support_trial import history_paths

BASE = panel.base
OUTPUT = proxy.OUTPUT
WORKER = Path(__file__).with_name("phase_forecast_worker.py")
DEVELOPMENT = ("DS26-0197", "DS26-0223")
EXCLUDE = set(DEVELOPMENT) | {
    "DS26-0036",
    "DS26-0120",
    "DS26-0150",
    "DS26-0279",
    "DS26-0307",
    "DS26-0207",
    "DS26-0040",
    "DS26-0080",
    "DS26-0026",
    "DS29-0174",
    "DS29-0316",
    "DS29-0604",
    "DS29-0519",
    "DS29-0127",
    "DS26-0070",
    "DS26-0277",
    "DS26-0203",
}
RUN_SALT = "phase-forecast-native/20261119/"
CAP = 90


def read(path):
    return json.loads(path.read_bytes())


def roster(original):
    reserve, omitted = [], []
    used = set(EXCLUDE)
    for cohort, count, chosen in (("roof", 2, reserve), ("omitted", 1, omitted)):
        for group in ("DS26-", "DS29-"):
            eligible = (
                r
                for r in original
                if r["recording"].startswith(group)
                and r["recording"] not in used
                and r["cohort"] == cohort
                and (cohort != "omitted" or r["id"].endswith("-omitted"))
            )
            rows = sorted(eligible, key=lambda r: proxy.digest((RUN_SALT + r["id"]).encode()))[
                :count
            ]
            if len(rows) != count:
                raise ValueError("insufficient distinct blind candidates")
            chosen.extend(r["id"] for r in rows)
            used.update(r["recording"] for r in rows)
    return dict(diagnostic=list(DEVELOPMENT), confirmation=reserve, omitted=omitted)


def prepare():
    stock_lock = read(panel.REPORT / "prediction-lock.json")
    BASE.secant_full._verify_files(panel.REPORT, stock_lock["files"])
    controls = read_predictions(panel.REPORT / "positions.jsonl.gz")
    original = read(panel.REPORT / "plan.json")["cases"]
    inputs = BASE.phase.frozen_inputs()
    cases = roster(original)
    work, records = [], []
    for cohort, ids in cases.items():
        for key in ids:
            query = next(r for r in original if r["id"] == key)
            item = inputs.get(query["recording"]) or BASE.native._load_case(query["recording"])
            packet, paths = BASE.native.request(item, "native", offer=query["packet"]["offer"])
            if (
                packet != query["packet"]
                or proxy.digest(encoded(packet)) != controls[key]["input_sha256"]
            ):
                raise ValueError(f"{key} request differs from the original archive")
            entries, files = history_paths(item)
            records.append(
                dict(
                    id=key,
                    cohort=cohort,
                    recording=query["recording"],
                    packet=packet,
                    history=entries,
                )
            )
            work.append((records[-1], paths | files, controls[key]))
    source_paths = (
        Path(__file__),
        WORKER,
        Path(law.__file__),
        Path(law.gauge.__file__),
        Path(history.__file__),
        Path(proxy.__file__),
        OUTPUT / "PROTOCOL.md",
    )
    lock = dict(
        source={str(p.relative_to(ROOT)): proxy.digest(p.read_bytes()) for p in source_paths},
        archive_sources=BASE.sources(BASE.BUNDLE),
        stock_prediction_sha256=stock_lock["files"]["positions.jsonl.gz"],
        cpus=list(proxy.CPUS),
        per_process_timeout_s=CAP,
        salt=RUN_SALT,
        cases=cases,
        inputs=records,
    )
    return work, lock


def measure(job, cpu):
    query, inputs, control = job
    command = BASE.command(cpu, inputs, BASE.BUNDLE)
    command[command.index(str(BASE.WORKER))] = str(WORKER)
    for p in (law, law.gauge, history):
        path = Path(p.__file__)
        command[-3:-3] = ["--ro-bind", str(path), str(Path("/worker") / path.relative_to(ROOT))]
    raw = encoded(dict(query["packet"], phase_history=query["history"]))
    began = perf_counter()
    try:
        response = subprocess.run(command, input=raw, capture_output=True, timeout=CAP, check=True)
        payload = json.loads(response.stdout)
        if payload["observation_sha256"] != control["observation_sha256"]:
            raise ValueError("native Graph digest differs from the archived control")
    except (OSError, ValueError, subprocess.SubprocessError) as err:
        message = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-1800:]
        payload = dict(
            result=dict(
                status="timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed",
                reason=message or str(err),
                boundary=law.BOUNDARY,
                metrics={},
                arms={a: dict(latlon=None, forced_latlon=None) for a in ARMS},
            )
        )
    validate_result(payload["result"])
    out = dict(
        **{
            k: control[k]
            for k in ("id", "recording", "input_sha256", "native_sha256", "catalog_sha256", "tile")
        },
        **payload,
        method=law.METHOD,
        study_cohort=query["cohort"],
        cpu=cpu,
        worker_wall_s=perf_counter() - began,
        history_request_sha256=proxy.digest(encoded(query["history"])),
    )
    print(
        out["id"],
        out["result"]["status"],
        out["result"]["reason"],
        out["result"]["metrics"].get("signed_prior_orbits"),
        round(out["worker_wall_s"], 2),
        flush=True,
    )
    return out


def proxy_binding(plan):
    model = read(OUTPUT / "catalogue-lock.json")
    BASE.secant_full._verify_files(OUTPUT, model["files"])
    recorded = read(OUTPUT / "catalogue-plan.json")
    if any(d != plan["source"].get(path) for path, d in recorded["sources"].items()):
        raise ValueError("blind mean differs from the held catalogue forecast")
    return proxy.digest((OUTPUT / "catalogue-lock.json").read_bytes())


def run(work):
    jobs, plan = prepare()
    if read(OUTPUT / "native-plan.json") != plan:
        raise ValueError("native forecast source or inputs differ from the predeclared plan")
    prior = proxy_binding(plan)
    work.mkdir(parents=True, exist_ok=False)
    start = perf_counter()

    def lane(j):
        for job in jobs[j::2]:
            r = measure(job, proxy.CPUS[j])
            save_json(work / (r["id"] + ".json"), r)

    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lane, range(2)))
    if prepare()[1] != plan or proxy_binding(plan) != prior:
        raise ValueError("experiment changed during blind evaluation")
    rows = [read(work / (q["id"] + ".json")) for q, _, _ in jobs]
    trace = [dict(id=r["id"], **r.pop("signed_phase")) for r in rows if "signed_phase" in r]
    files = {
        name: pack(OUTPUT, name, values)
        for name, values in (
            ("positions.jsonl.gz", rows),
            ("phase-means.jsonl.gz", trace),
            ("control-positions.jsonl.gz", [dict(c, study_cohort=q["cohort"]) for q, _, c in jobs]),
        )
    }
    files["native-plan.json"] = proxy.digest((OUTPUT / "native-plan.json").read_bytes())
    save_json(
        OUTPUT / "prediction-lock.json",
        dict(
            cases=[r["id"] for r in rows],
            files=files,
            catalogue_lock_sha256=prior,
            wall_s=perf_counter() - start,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()
    if args.work:
        run(args.work)
    else:
        proposed = prepare()[1]
        save_json(OUTPUT / "native-plan.json", proposed)
        print(proposed["cases"])
