"""Profile and qualify a chronological gate on sealed native and causal inputs."""

import argparse
import gzip
import hashlib
import json
import os
import secrets
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

import numpy as np

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants import orbit_projector, portable_gate
from .cold_scenes import _shuffled
from .portable_v5_transfer import new_scenes
from .portable_v5_trials import NATIVE, checksum, sandbox, source_lock
from .portable_v5_trials import REPORT as PRIOR

REPORT = ROOT / "reports/2026_11_19_receiver_screening/inference/portable-gate"
PROFILE = Path(__file__).with_name("portable_gate_profile.py")
WORKER = Path(__file__).with_name("portable_gate_worker.py")
CASE_S = 195
MODES = {"matched-tile": "present", "omitted-tile": "missing", "shuffle": "shuffle"}


def worker_command(cpu, objects, kernel, worker, modules=()):
    command = sandbox(cpu, objects, kernel)
    bindings = [(worker, "/trial/main.py")]
    for module in modules:
        path = Path(module.__file__)
        bindings.append((path, f"/worker/tools/pipeline_eval/variants/{path.name}"))
    for path, target in bindings:
        command[-4:-4] = ("--ro-bind", str(path), target)
    command[-2] = "/trial/main.py"
    assert command[-1] == str(NATIVE)
    return command


def invoke(command, data, timeout):
    start = perf_counter()
    try:
        p = subprocess.run(command, input=data, capture_output=True, timeout=timeout, check=False)
        status = "complete" if p.returncode == 0 else "failed"
        return p.stdout, p.stderr, status, perf_counter() - start
    except subprocess.TimeoutExpired as exc:
        return b"", exc.stderr or b"", "timed_out", perf_counter() - start


def profile(jobs, kernel, cpus):
    def single(cpu, job):
        ident, mode, document, offer, history, objects = job
        packet = encoded(dict(document=document, tile=offer, history=history))
        command = worker_command(cpu, objects, kernel, PROFILE)
        out, err, status, elapsed = invoke(command, packet, 188)
        result = dict(
            id=ident,
            mode=mode,
            status=status,
            worker_wall_s=elapsed,
            trace=[
                json.loads(s)
                for s in err.decode(errors="replace").splitlines()
                if s.startswith("{")
            ],
            result=json.loads(out) if out else None,
            input_sha256=hashlib.sha256(packet).hexdigest(),
            command=command,
        )
        print(ident, mode, status, round(elapsed, 1), flush=True)
        return result

    selected = jobs[1:]
    batches = selected[::2], selected[1::2]
    with ThreadPoolExecutor(max_workers=len(cpus)) as pool:
        blocks = [
            pool.submit(sequence, single, cpu, batch)
            for cpu, batch in zip(cpus, batches, strict=True)
        ]
    return [r for b in blocks for r in b.result()]


def sequence(worker, cpu, batch):
    return [worker(cpu, job) for job in batch]


def historical_jobs():
    labels = json.loads((PRIOR / "synthetic-labels.json").read_bytes())
    return new_scenes(bytes.fromhex(labels["seed_hex"]))


def synthesise(seed):
    jobs, labels, history = new_scenes(seed)
    ident, _, document, offer, stamps, objects = jobs[0]
    rng = np.random.default_rng(int.from_bytes(seed, "big") + 1)
    shuffled = dict(document["source"], probes=_shuffled(document["source"]["probes"], rng))
    jobs.append(
        (ident + "-shuffle", "shuffle", dict(document, source=shuffled), offer, stamps, objects)
    )
    return jobs, labels, history


def lock():
    paths = (
        Path(__file__),
        WORKER,
        Path(new_scenes.__code__.co_filename),
        Path(_shuffled.__code__.co_filename),
        Path(portable_gate.__file__),
    )
    return dict(stock=source_lock(), files={p.name: checksum(p) for p in paths})


def compressed_rows(rows):
    return gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0)


def stock_rows():
    rows = []
    for mode in ("matched-tile", "omitted-tile"):
        with gzip.open(PRIOR / f"{mode}.jsonl.gz", "rt") as f:
            rows.extend(json.loads(line) for line in f)
    return keyed(rows)


def keyed(rows):
    return {(r["id"], r["mode"]): r for r in rows}


def trial(jobs, kernel, cpus):
    def single(cpu, job):
        ident, mode, document, offer, history, objects = job
        data = encoded(dict(document=document, tile=offer, history=history))
        command = worker_command(cpu, objects, kernel, WORKER, (portable_gate,))
        out, err, status, elapsed = invoke(command, data, CASE_S)
        if status == "complete":
            result = json.loads(out)
        else:
            reason = (
                err.decode(errors="replace")[-2400:] if status == "failed" else "wall cap reached"
            )
            result = dict(
                status=status,
                reason=reason or status,
                boundary=portable_gate.BOUNDARY,
                metrics={},
                arms={arm: dict(latlon=None) for arm in ARMS},
            )
        validate_result(result)
        row = dict(
            id=ident,
            method=portable_gate.METHOD,
            mode=mode,
            offer=offer,
            result=result,
            cpu=cpu,
            worker_wall_s=elapsed,
            input_sha256=hashlib.sha256(data).hexdigest(),
            document_sha256=hashlib.sha256(encoded(document)).hexdigest(),
            history_sha256=hashlib.sha256(encoded(history)).hexdigest(),
        )
        print(ident, mode, result["status"], round(elapsed, 2), flush=True)
        return row

    left, right = [], []
    for i in range(0, len(jobs) - 1, 2):
        a, b = jobs[i : i + 2]
        if i % 4:
            a, b = b, a
        left.append(a)
        right.append(b)
    if len(jobs) % 2:
        right.append(jobs[-1])
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [
            pool.submit(sequence, single, cpu, batch)
            for cpu, batch in zip(cpus, (left, right), strict=True)
        ]
    by_id = keyed(r for p in pending for r in p.result())
    return [by_id[j[0], j[1]] for j in jobs]


def blocks(historical, history_labels, fresh, fresh_labels):
    stock = stock_rows()
    positions, baselines, queries = [], [], []
    for cohort, rows, labels in (
        ("historical", historical, history_labels),
        ("fresh", fresh, fresh_labels),
    ):
        for raw in rows:
            ident, mode = raw["id"], raw["mode"]
            if mode != "shuffle":
                i = list(labels).index(ident) + 1
                recording = f"{cohort} site {i}"
            else:
                recording = "fresh shuffle"
            query = f"{cohort}-{ident}-{mode}"
            fields = ("history_sha256", "document_sha256", "input_sha256")
            if cohort == "historical":
                previous = stock[ident, mode]
                if any(previous[k] != raw[k] for k in fields):
                    raise ValueError("historical packet differs from the original portable input")
                baselines.append(dict(previous, id=query))
            positions.append(dict(raw, id=query, capture_id=ident, cohort=cohort))
            queries.append(
                dict(
                    id=query,
                    recording=recording,
                    condition=MODES[mode],
                    truth=labels.get(ident, {}).get("position"),
                    bindings={k: raw[k] for k in fields},
                )
            )
    return positions, baselines, queries


def score(report):
    seal = json.loads((report / "prediction-lock.json").read_bytes())
    for name, digest in seal["files"].items():
        if checksum(report / name) != digest:
            raise ValueError("prediction bytes differ from the pre-score lock")
    labels = json.loads((report / "labels.json").read_bytes())

    def rows(name):
        with gzip.open(report / name, "rt") as f:
            return [json.loads(line) for line in f]

    historical, fresh = rows("historical.jsonl.gz"), rows("fresh.jsonl.gz")
    positions, baselines, queries = blocks(historical, labels["historical"], fresh, labels["fresh"])
    files = {}
    metrics = []
    by_query = {q["id"]: q for q in queries}
    for name, group, baseline in (
        ("historical", [p for p in positions if p["cohort"] == "historical"], baselines),
        ("fresh", [p for p in positions if p["cohort"] == "fresh"], []),
    ):
        if baseline:
            files[f"{name}-stock-positions.jsonl.gz"] = compressed_rows(baseline)
        files[f"{name}-positions.jsonl.gz"] = compressed_rows(group)
        files[f"{name}-figure-queries.json"] = encoded(
            dict(queries=[by_query[r["id"]] for r in group])
        )
        names = [key for key in files if key.startswith(f"{name}-")]
        files[f"{name}-figure-lock.json"] = encoded(
            dict(
                cases=[r["id"] for r in group],
                files={key: hashlib.sha256(files[key]).hexdigest() for key in names},
            )
        )
        for row in [*group, *baseline]:
            q = by_query[row["id"]]
            result = row["result"]
            for arm in ARMS:
                fit = result["arms"][arm]
                metrics.append(
                    dict(
                        query=row["id"],
                        cohort=name,
                        mode=row["mode"],
                        arm=arm,
                        method=row["method"],
                        offer_center_error_km=distance_km(row["offer"]["center"], q["truth"]),
                        position_error_km=distance_km(fit["latlon"], q["truth"]),
                        conditional_rf_rms_hz=fit.get("rf_rms_hz"),
                        status=result["status"],
                        published=fit["latlon"] is not None,
                        false_publication=(
                            row["mode"] in {"omitted-tile", "shuffle"} and fit["latlon"] is not None
                        ),
                        runtime_s=row["worker_wall_s"],
                    )
                )
    for name, contents in files.items():
        write(report / name, contents)
    grouped = {}
    for row in metrics:
        key = "/".join(row[k] for k in ("cohort", "mode", "method", "arm"))
        grouped.setdefault(key, []).append(row)
    summary = {
        key: dict(
            attempts=len(group),
            publications=sum(r["published"] for r in group),
            withheld=sum(r["status"] == "withheld" for r in group),
            timed_out=sum(r["status"] == "timed_out" for r in group),
            false_publications=sum(r["false_publication"] for r in group),
            **{
                k: distribution(r[k] for r in group)
                for k in ("position_error_km", "conditional_rf_rms_hz", "runtime_s")
            },
        )
        for key, group in grouped.items()
    }
    save_json(report / "scores.json", dict(rows=metrics, summary=summary))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--cpus", type=int, nargs=2, default=(4, 5))
    parser.add_argument("--phase", choices=("profile", "infer", "score"), default="profile")
    parser.add_argument("--fresh-seed-hex")
    args = parser.parse_args()
    if len(set(args.cpus)) != 2 or not set(args.cpus) <= os.sched_getaffinity(0):
        parser.error("choose two distinct available CPUs")
    scratch, report = local_output(args.scratch), local_output(args.report)
    if args.phase == "score":
        score(report)
        return
    scratch.mkdir(exist_ok=True, parents=True)
    kernel = scratch / "projector.so"
    orbit_projector.compile_kernel(kernel)
    jobs, history_labels, history = historical_jobs()
    if args.phase == "profile":
        save_json(
            report / "original-profiles.json",
            dict(
                worker_sha256=checksum(PROFILE),
                stock=source_lock(),
                rows=profile(jobs, kernel, args.cpus),
            ),
        )
        return
    source = lock()
    save_json(report / "source-lock.json", source)
    seed = bytes.fromhex(args.fresh_seed_hex) if args.fresh_seed_hex else secrets.token_bytes(32)
    fresh, fresh_labels, fresh_history = synthesise(seed)
    if history != fresh_history:
        raise ValueError(
            "the historical and fresh cohorts should share the archived causal history"
        )
    save_json(report / "authentic-history.json", history)
    source_labels = dict(historical=history_labels, fresh=fresh_labels, seed_hex=seed.hex())
    rows = trial([*jobs, *fresh], kernel, args.cpus)
    if lock() != source:
        raise ValueError("receiver sources changed since the prospective lock")
    names = ("historical.jsonl.gz", "fresh.jsonl.gz")
    groups = rows[: len(jobs)], rows[len(jobs) :]
    for name, group in zip(names, groups, strict=True):
        write(report / name, compressed_rows(group))
    seal = {n: checksum(report / n) for n in names}
    save_json(report / "prediction-lock.json", dict(files=seal))
    save_json(report / "labels.json", source_labels)


if __name__ == "__main__":
    main()
