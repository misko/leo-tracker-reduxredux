"""Record two blind repeated-session simulations under the stationary receiver protocol."""

import argparse
import gzip
import json
import os
import secrets
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

import numpy as np

from .. import figure_books, whole_iq
from ..__main__ import THREAD_ENV, encoded, local_output, save_json, write
from ..scoring import ARMS
from ..variants import compact_tile_interior
from ..variants.trackless_likelihood import _offset
from . import cold_scenes
from . import multi_session_results as results
from . import multi_session_trial as trial
from .full_v5_check import _sha
from .prefix_figures import csv_file
from .site_transfer_samples import _catalogue

OUT = trial.OUT / "simulation"
PROFILE = "profiles.jsonl.gz"
PLAN = "plan.json"
DECISIONS = "decisions.json"
LOCK = "prediction-lock.json"


def stage(work, report):
    if (report / PLAN).exists():
        raise FileExistsError("simulated geometry is already sealed")
    work.mkdir(parents=True, mode=0o700)
    report.mkdir(parents=True, exist_ok=True)
    private = work / "private"
    private.mkdir(mode=0o700)
    seed = secrets.token_bytes(32)
    write(private / "seed.bin", seed)
    rng = np.random.default_rng(int.from_bytes(seed, "big"))
    catalogue, collected = _catalogue()
    write(work / "causal.tle", catalogue)
    orbits = cold_scenes._constellation(catalogue, collected)
    jobs, truths = [], {}
    for ix, corner in enumerate(((17, -102), (-25, 141))):
        center = (np.asarray(corner) + rng.uniform(-1.5, 1.5, size=2)).tolist()
        truth = list(_offset(center, rng.uniform(4, 6), rng.uniform(-6, 6)))
        site = rng.bytes(10).hex()
        truths[site] = dict(truth=truth, sessions={})
        for group, initial in (("early", 3000), ("late", 46_200)):
            start = collected + (initial + ix * 4200) * trial.NANO
            probes, counter, latent = cold_scenes._generate_capture(orbits, start, truth, rng)
            ident = rng.bytes(10).hex()
            data = dict(
                case_id=ident,
                probes=probes,
                sample_rate_hz=cold_scenes.RATE,
                probe_ms=cold_scenes.PROBE_MS,
                first_counter=counter,
                anchor_utc_ns=start,
                cutoff_utc_ns=start,
                catalog_timestamp_ns=collected,
                duration_s=cold_scenes.SECONDS,
            )
            native = work / (ident + ".json.gz")
            write(native, gzip.compress(encoded(data), mtime=0))
            jobs.append(
                dict(
                    id=ident,
                    site=site,
                    tile=dict(center=center, width_km=25),
                    group=group,
                    native_sha256=_sha(native),
                )
            )
            truths[site]["sessions"][ident] = latent
    save_json(private / "truth.json", truths)
    sources = (
        Path(__file__),
        Path(cold_scenes.__file__),
        Path(trial.__file__),
        Path(results.__file__),
        Path(_catalogue.__code__.co_filename),
        trial.ROOT / "tools/pipeline_eval/variants/multi_session.py",
        trial.ROOT / "tools/pipeline_eval/variants/trackless_likelihood.py",
        trial.OUT / "SIMULATION.md",
    )
    save_json(
        report / PLAN,
        dict(
            jobs=jobs,
            labels_sha256=_sha(private / "truth.json"),
            seed_sha256=_sha(private / "seed.bin"),
            catalog_sha256=_sha(work / "causal.tle"),
            cpus=list(trial.CPUS),
            cap_s=trial.CAP_S,
            sources={str(p.relative_to(trial.ROOT)): _sha(p) for p in sources},
        ),
    )
    write(work / "plan.sha256", _sha(report / PLAN).encode())


def attempt(work, case, catalogue, cpu):
    native = whole_iq.checked(work / (case["id"] + ".json.gz"), case["native_sha256"])
    payload = json.loads(gzip.decompress(native.read_bytes()))
    begin = perf_counter()
    try:
        proc = subprocess.run(
            ["taskset", "-c", str(cpu), sys.executable, "-B", "-m", trial.MODULE, "worker"],
            env=os.environ | THREAD_ENV,
            input=encoded(
                dict(
                    capture=payload | {"catalog": catalogue}, center=case["tile"]["center"], cpu=cpu
                )
            ),
            capture_output=True,
            check=True,
            timeout=trial.CAP_S,
        )
        measured = json.loads(proc.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        detail = (getattr(error, "stderr", None) or b"").decode(errors="replace")[-2400:]
        status = "timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed"
        measured = dict(status=status, reason=detail or str(error))
    result = dict(
        case,
        cpu=cpu,
        **measured,
        duration_s=payload["duration_s"],
        cutoff_utc_ns=payload["cutoff_utc_ns"],
        elapsed_s=perf_counter() - begin,
    )
    save_json(work / (case["id"] + "-profile.json"), result)
    print(
        case["id"],
        result["status"],
        round(result["elapsed_s"], 2),
        result.get("reason", ""),
        flush=True,
    )
    return result


def predict(work, report):
    if (report / LOCK).exists():
        raise FileExistsError("simulated outcomes already sealed")
    plan = whole_iq.read(whole_iq.checked(report / PLAN, (work / "plan.sha256").read_text()))
    for name, digest in plan["sources"].items():
        whole_iq.checked(trial.ROOT / name, digest)
    path = whole_iq.checked(work / "causal.tle", plan["catalog_sha256"])
    catalogue = path.read_text()
    lanes = list(zip(trial.CPUS, (plan["jobs"][::2], plan["jobs"][1::2]), strict=True))

    def lane(job):
        cpu, cases = job
        return [attempt(work, case, catalogue, cpu) for case in cases]

    with ThreadPoolExecutor(max_workers=len(trial.CPUS)) as pool:
        rows = [row for group in pool.map(lane, lanes) for row in group]
    for name, digest in plan["sources"].items():
        whole_iq.checked(trial.ROOT / name, digest)
    write(report / PROFILE, gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0))
    sites = defaultdict(list)
    for row in rows:
        sites[row["site"]].append(row)
    decisions = [
        dict(site=site, **r)
        for site, cohort in sites.items()
        for r in results.stationary(sorted(cohort, key=lambda r: r["cutoff_utc_ns"]))
    ]
    save_json(report / DECISIONS, decisions)
    save_json(report / LOCK, dict(files={n: _sha(report / n) for n in (PLAN, PROFILE, DECISIONS)}))


def score(work, report):
    seal = whole_iq.read(report / LOCK)
    for path, digest in seal["files"].items():
        whole_iq.checked(report / path, digest)
    plan = whole_iq.read(report / PLAN)
    truth = whole_iq.read(whole_iq.checked(work / "private/truth.json", plan["labels_sha256"]))
    decisions = whole_iq.read(report / DECISIONS)
    positions, queries, scores, seen = [], [], [], set()
    for row in decisions:
        site, condition = row["site"], row["offer"]
        ident = site + "-" + condition
        geo = truth[site]["truth"]
        bindings = dict(input_sha256=seal["files"][PROFILE], tile=row["tile"])
        margin = compact_tile_interior.margin(geo, row["tile"])
        if (margin >= 0) != (condition == "containing"):
            raise ValueError("simulated offer condition differs from the registered geometry")
        if ident not in seen:
            queries.append(
                dict(id=ident, condition=condition, recording=site, truth=geo, bindings=bindings)
            )
            seen.add(ident)
        positions.append(dict(id=ident, method=row["method"], result=row["result"], **bindings))
        scores.append(results.score_row(dict(row, id=ident), geo, None))
    csv_file(report / "scores.csv", scores)
    filename = "positions.jsonl.gz"
    write(
        report / filename, gzip.compress(b"".join(encoded(r) + b"\n" for r in positions), mtime=0)
    )
    save_json(report / "queries.json", dict(queries=queries))
    names = (filename, "queries.json", LOCK, "scores.csv")
    save_json(
        report / "figure-lock.json",
        dict(
            cases=[q["id"] for q in queries],
            files={n: _sha(report / n) for n in names},
        ),
    )
    pairs = (
        ("candidate", "all_sessions"),
        ("stock", "session_1"),
        ("one", "time_shuffle"),
        ("four", "center"),
    )
    save_json(
        report / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id="stationary-simulated-sites",
                    method="stationary-simulated-sites",
                    scope="transfer",
                    cases="sealed",
                    seal="figure-lock.json",
                    queries="queries.json",
                    provenance=[LOCK, "scores.csv"],
                    condition_labels=results.CONDITIONS,
                    title="Stationary likelihood across two independent simulated sites",
                    caption="Each site has two sessions with fresh emitters and receiver clocks.",
                    series=[
                        dict(
                            key=k,
                            file=filename,
                            value=method,
                            label=results.BASE_METHODS[method],
                            forced_label=results.BASE_METHODS[method] + " (diagnostic)",
                        )
                        for k, method in pairs
                    ],
                )
            ],
        ),
    )
    seed = whole_iq.checked(work / "private/seed.bin", plan["seed_sha256"])
    save_json(report / "released-labels.json", dict(seed_hex=seed.read_bytes().hex(), labels=truth))
    figure_books.generate(report / "charts", ARMS, panel="screening", evidence=report)
    save_json(
        report / "score-lock.json",
        dict(
            files={
                n: _sha(report / n)
                for n in (
                    *names,
                    "released-labels.json",
                    "figures.json",
                    "figure-lock.json",
                    "charts/manifest.json",
                )
            }
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "predict", "score"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("--report", type=local_output, default=OUT)
    args = parser.parse_args()
    return {"stage": stage, "predict": predict, "score": score}[args.action](args.work, args.report)


if __name__ == "__main__":
    main()
