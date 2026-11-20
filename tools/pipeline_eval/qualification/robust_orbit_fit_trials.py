"""Run paired locked lean receivers on the timing and hash-selected confirmation cohorts."""

import argparse
import gzip
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from .. import corpus
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import ARMS, distribution, validate_result
from ..variants import robust_em, robust_orbit_fit
from .prefix_figures import csv_file
from .robust_em_trials import TIMING_IDS, WORKER, WRONG_CASE, load, sandbox, score, source_hashes

OUTPUT = ROOT / "reports/2026_11_19_receiver_convergence/track-fit"
TRIAL_WORKER = Path(__file__).with_name("robust_orbit_fit_worker.py")
METHODS = (robust_em.METHOD, robust_orbit_fit.METHOD)
CONFIRMATION = (
    "DS26-0189",
    "DS26-0231",
    "DS26-0243",
    "DS26-0223",
    "DS26-0257",
    "DS26-0201",
    "DS26-0150",
    "DS26-0241",
)


def confirm_roster():
    panel, _ = corpus._selection("ds26-common127")
    roof, _ = corpus._selection("roof16")
    candidates = set(panel) - set(roof) - set(TIMING_IDS) - {"DS26-0066"}
    selected = sorted(
        candidates,
        key=lambda case: sha256(
            ("robust-orbit-fit-confirmation/v1:" + case).encode("ascii")
        ).digest(),
    )[:8]
    if tuple(selected) != CONFIRMATION:
        raise ValueError("confirmation input inventory changed after preregistration")
    return selected


def locked_sources():
    old = source_hashes()
    prior = ROOT / "reports/2026_11_19_short_receiver/robust-em/source-lock.json"
    if old != json.loads(prior.read_bytes()):
        raise ValueError("locked lean control changed")
    return dict(
        old,
        **{
            path.name: sha256(path.read_bytes()).hexdigest()
            for path in (Path(robust_orbit_fit.__file__), TRIAL_WORKER)
        },
    )


def command(cpu, method):
    argv = sandbox(cpu)
    argv[argv.index(str(WORKER))] = str(TRIAL_WORKER)
    source = Path(robust_orbit_fit.__file__)
    argv[-3:-3] = ["--ro-bind", str(source), f"/worker/tools/pipeline_eval/variants/{source.name}"]
    return [*argv, method]


def execute(method, case, cohort, mode, packet, bindings, cpu, keys):
    raw = encoded(packet)
    t0 = perf_counter()
    try:
        out = json.loads(
            subprocess.run(
                command(cpu, method), input=raw, capture_output=True, check=True, timeout=45
            ).stdout
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as err:
        out = dict(
            worker_cpu_s=None,
            max_rss_kib=None,
            result=dict(
                status="failed" if isinstance(err, subprocess.CalledProcessError) else "timed_out",
                reason=(err.stderr or b"").decode(errors="replace")[-2000:] or str(err),
                boundary=robust_orbit_fit.BOUNDARY,
                metrics={},
                arms={arm: {"latlon": None} for arm in ARMS},
            ),
        )
    wall = perf_counter() - t0
    validate_result(out["result"])
    print(method, case, mode, out["result"]["status"], round(wall, 2), flush=True)
    return dict(
        id=case,
        method=method,
        cohort=cohort,
        mode=mode,
        tile=packet["offer"],
        cpu=cpu,
        worker_wall_s=wall,
        implementation_sha256=keys[f"{method}.py"],
        input_sha256=sha256(raw).hexdigest(),
        **bindings,
        **out,
    )


def evaluate(rows):
    table = []
    for method in METHODS:
        group = [r for r in rows if r["method"] == method]
        cohorts = {(r["id"], r["mode"]): r["cohort"] for r in group}
        table.extend(
            dict(r, method=method, cohort=cohorts[r["id"], r["mode"]]) for r in score(group)
        )
    output = {}
    for cohort in ("timing", "confirmation", "wrong-region"):
        output[cohort] = {}
        for arm in ARMS:
            control, upgraded = (
                {
                    r["id"]: r
                    for r in table
                    if r["method"] == method and r["cohort"] == cohort and r["arm"] == arm
                }
                for method in METHODS
            )
            common = [
                case
                for case in control
                if control[case]["error_km"] is not None and upgraded[case]["error_km"] is not None
            ]

            def collect(records):
                errors = [r["error_km"] for r in records.values() if r["error_km"] is not None]
                return dict(
                    fixes=len(errors),
                    within_5km=sum(e <= 5 for e in errors),
                    geographic_error_km=distribution(errors),
                )

            output[cohort][arm] = dict(
                stock=collect(control),
                candidate=collect(upgraded),
                frozen_v5=distribution([r["original_v5_error_km"] for r in control.values()])
                if cohort != "wrong-region"
                else None,
                common_fixes=len(common),
                paired_error_delta_km=distribution(
                    [upgraded[k]["error_km"] - control[k]["error_km"] for k in common]
                ),
            )
    return table, output


def lock_predictions(output):
    files = (
        "positions.jsonl.gz",
        "stock-positions.jsonl.gz",
        "wrong-region.jsonl.gz",
        "stock-wrong-region.jsonl.gz",
    )
    save_json(
        output / "prediction-lock.json",
        dict(
            files={name: sha256((output / name).read_bytes()).hexdigest() for name in files},
            cases={
                "timing": TIMING_IDS,
                "confirmation": CONFIRMATION,
                "wrong-region": [WRONG_CASE],
            },
        ),
    )


def trial(output, cache, cpus):
    output, cache = local_output(output), local_output(cache)
    if len(set(cpus)) != 2 or not set(cpus) <= os.sched_getaffinity(0):
        raise ValueError("choose two pinned CPU lanes")
    keys = locked_sources()
    plan = [(case, "timing", "matched-tile") for case in TIMING_IDS]
    plan += [(case, "confirmation", "matched-tile") for case in confirm_roster()]
    plan += [(WRONG_CASE, "wrong-region", "wrong-region")]
    save_json(output / "source-lock.json", keys)

    def run_lane(i):
        result = []
        for index in range(i, len(plan), 2):
            case, cohort, mode = plan[index]
            packet, bindings = load(case, mode, cache)
            order = METHODS if index % 2 == 0 else METHODS[::-1]
            for name in order:
                result.append(execute(name, case, cohort, mode, packet, bindings, cpus[i], keys))
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        predictions = [r for lane in pool.map(run_lane, (0, 1)) for r in lane]
    if locked_sources() != keys:
        raise ValueError("inference sources changed during paired replay")
    order = {(case, mode): j for j, (case, _, mode) in enumerate(plan)}
    predictions.sort(key=lambda r: (order[r["id"], r["mode"]], r["method"]))
    for i, name in enumerate(METHODS):
        prefix = "stock-" if i == 0 else ""
        for mode, stem in (("matched-tile", "positions"), ("wrong-region", "wrong-region")):
            rows = [p for p in predictions if p["method"] == name and p["mode"] == mode]
            write(
                output / f"{prefix}{stem}.jsonl.gz",
                gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0),
            )
    lock_predictions(output)
    table, summary = evaluate(predictions)
    csv_file(output / "scores.csv", table)
    save_json(output / "summary.json", summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--cpus", nargs=2, type=int, default=(10, 11))
    args = parser.parse_args()
    trial(args.out, args.cache, args.cpus)


if __name__ == "__main__":
    main()
