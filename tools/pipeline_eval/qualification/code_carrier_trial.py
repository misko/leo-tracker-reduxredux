"""Replay signed code and carrier measurements with blinded causal geometry."""

import argparse
import gzip
import json
import os
import secrets
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from resource import RLIMIT_AS, RUSAGE_SELF, getrusage, setrlimit
from time import perf_counter, process_time
from types import SimpleNamespace

from .. import corpus, whole_iq
from ..__main__ import ROOT, THREAD_ENV, encoded, local_output, save_json, write
from . import cold_input, sequential_fix_trial
from .full_v5_check import BULK, _load_case, _sha

OUT = sequential_fix_trial.SCREEN / "original-schedule/code-carrier"
MODULE = "tools.pipeline_eval.qualification.code_carrier_trial"
CPUS = (20, 21)
MEMORY = 512 * 1024**2
CAP = 90
PLAN = "blind-plan.json"
PREDICTIONS = "predictions.jsonl.gz"
LOCK = "prediction-lock.json"
EXCLUDE = frozenset(
    (
        "DS26-0002",
        "DS26-0004",
        "DS26-0030",
        "DS26-0032",
        "DS26-0036",
        "DS26-0058",
        "DS26-0237",
        "DS29-0082",
        "DS29-0127",
        "DS29-0174",
        "DS29-0247",
        "DS29-0316",
    )
)


def capture_metadata(case, capture):
    path = whole_iq.checked(BULK / case["native"]["path"], capture.native_sha256)
    document = whole_iq.read(path)
    generation = document["source"]["stream_generation"]
    if not generation or any(p["probe_start_ms"] != 0 for p in capture.probes):
        raise ValueError("clock generation or probe origin unsupported")
    # Packed payload offsets omit retune gaps. The physical coordinate is the
    # hardware counter, and the two receiver observations must agree per visit.
    visits = {}
    for row in capture.probes:
        key = row["visit_index"]
        values = row["valid_start_counter"], row["payload_start_sample"]
        if visits.setdefault(key, values) != values:
            raise ValueError("same-visit receiver sample coordinates disagree")
    positions = [visits[key] for key in sorted(visits)]
    increments = [
        (b[0] - a[0], b[1] - a[1]) for a, b in zip(positions[:-1], positions[1:], strict=True)
    ]
    if not increments or any(min(x) <= 0 for x in increments):
        raise ValueError("native capture hardware and payload coordinates must increase")
    return dict(
        generation=generation,
        first_visit_counter=positions[0][0],
        counters_with_retune_gap=sum(a != b for a, b in increments),
        excluded_visits=len(document["provenance"]["excluded_windows"]),
    )


def selection():
    rows, attempted = [], []
    inventory = sequential_fix_trial.inventory()
    for panel in ("DS26", "DS29"):
        last = 0
        eligible = sorted(
            (r["cutoff_utc_ns"], r["id"], r)
            for r in inventory.values()
            if (
                r["panel"] == panel
                and r["id"].startswith(panel + "-")
                and r["id"] not in EXCLUDE
                and all(r.get(k) for k in ("native", "catalog", "regions", "cutoff_utc_ns"))
            )
        )
        for when, ident, case in eligible:
            if when - last < 12 * 3600 * 10**9:
                continue
            item = dict(id=ident, cutoff_utc_ns=when)
            attempted.append(item)
            try:
                cap = cold_input.load(ident)
                if not 295 <= cap.duration_s <= 305:
                    raise ValueError("native duration differs from full five minutes")
                meta = capture_metadata(case, cap)
            except (OSError, ValueError, KeyError) as error:
                item["ineligible"] = str(error)
                continue
            rows.append(
                dict(
                    item,
                    group=panel,
                    center=case["regions"][0]["center"],
                    native_sha256=cap.native_sha256,
                    catalog_sha256=cap.catalog_sha256,
                    catalogue_utc_ns=cap.catalog_timestamp_ns,
                    **meta,
                )
            )
            last = when
            if sum(r["group"] == panel for r in rows) == 2:
                break
        if sum(r["group"] == panel for r in rows) != 2:
            raise ValueError(f"expected two admitted disjoint {panel} captures")
    return rows, attempted


def simulation(work, seed_file):
    import numpy as np

    from ..variants.folded_doppler import _offset
    from . import cold_scenes
    from .site_transfer_samples import _catalogue

    private = work / "private"
    private.mkdir(mode=0o700)
    seed = secrets.token_bytes(32) if seed_file is None else seed_file.read_bytes()
    if len(seed) != 32:
        raise ValueError("the simulation seed needs 32 bytes")
    write(private / "seed.bin", seed)
    rng = np.random.default_rng(int.from_bytes(seed, "big"))
    center = (np.asarray([-32.0, 19.0]) + rng.uniform(-1.5, 1.5, 2)).tolist()
    truth = list(_offset(center, rng.uniform(4.0, 6.0), rng.uniform(-4.5, 4.5)))
    tle, collected = _catalogue()
    start = collected + 9420 * 10**9
    orbits = cold_scenes._constellation(tle, collected)
    probes, counter, latent = cold_scenes._generate_capture(orbits, start, truth, rng)
    ident = rng.bytes(10).hex()
    generation = f"generated-{ident}"
    doc = dict(
        case_id=ident,
        generation=generation,
        probes=probes,
        sample_rate_hz=cold_scenes.RATE,
        probe_ms=cold_scenes.PROBE_MS,
        first_counter=counter,
        anchor_utc_ns=start,
        cutoff_utc_ns=start,
        catalog_timestamp_ns=collected,
        duration_s=cold_scenes.SECONDS,
    )
    write(work / "simulation.json.gz", gzip.compress(encoded(doc), mtime=0))
    write(work / "simulation.tle", tle)
    save_json(private / "truth.json", dict(truth=truth, generator=latent))
    item = dict(
        id=ident,
        group="simulation",
        center=center,
        cutoff_utc_ns=start,
        catalogue_utc_ns=collected,
        generation=generation,
        native_sha256=_sha(work / "simulation.json.gz"),
        catalog_sha256=_sha(work / "simulation.tle"),
    )
    return item, {name: _sha(private / name) for name in ("seed.bin", "truth.json")}


def stage(work, report, seed_file):
    if (report / PLAN).exists():
        raise FileExistsError("the signed range roster is already registered")
    real, audit = selection()
    work.mkdir(parents=True, mode=0o700)
    sim, private = simulation(work, seed_file)
    names = (
        "tools/pipeline_eval/variants/code_carrier.py",
        "tools/pipeline_eval/variants/clock_transfer_grouped.py",
        "tools/pipeline_eval/variants/track_epoch.py",
        "tools/pipeline_eval/variants/peak_paths.py",
        "tools/pipeline_eval/variants/joint_pass.py",
        "tools/pipeline_eval/variants/doppler_turns.py",
        "tools/pipeline_eval/variants/multi_session.py",
        "tools/pipeline_eval/reference/grid.py",
        "tools/pipeline_eval/reference/tracker.py",
        "tools/pipeline_eval/qualification/cold_scenes.py",
        "tools/pipeline_eval/qualification/site_transfer_samples.py",
        "src/leo/sky/frames.py",
        "src/leo/sky/propagation.py",
    )
    paths = [
        Path(__file__),
        Path(cold_input.__file__),
        report / "PROTOCOL.md",
        corpus.FROZEN / "provenance.json",
        *(ROOT / name for name in names),
    ]
    plan = dict(
        cases=[*real, sim],
        eligibility=audit,
        private_sim=private,
        cpus=list(CPUS),
        cap_s=CAP,
        memory_bytes=MEMORY,
        sources={str(p.resolve()): _sha(p) for p in paths},
    )
    save_json(report / PLAN, plan)
    write(work / "plan.sha256", _sha(report / PLAN).encode())
    print([(r["id"], r["group"]) for r in plan["cases"]], flush=True)


def native(case, work):
    if case["group"] == "simulation":
        raw = whole_iq.checked(work / "simulation.json.gz", case["native_sha256"])
        tle = whole_iq.checked(work / "simulation.tle", case["catalog_sha256"])
        return json.loads(gzip.decompress(raw.read_bytes())) | {"catalog": tle.read_text()}
    cap = cold_input.load(case["id"])
    meta = capture_metadata(_load_case(case["id"]), cap)
    if any(
        case[name] != value
        for name, value in (
            ("native_sha256", cap.native_sha256),
            ("catalog_sha256", cap.catalog_sha256),
            ("cutoff_utc_ns", cap.cutoff_utc_ns),
            ("catalogue_utc_ns", cap.catalog_timestamp_ns),
            *meta.items(),
        )
    ):
        raise ValueError("clock or native context differs from the locked input")
    return vars(cap) | {"catalog": cap.catalog.decode("ascii"), "generation": meta["generation"]}


def worker():
    start, cpu = perf_counter(), process_time()
    setrlimit(RLIMIT_AS, (MEMORY, MEMORY))
    from ..variants import code_carrier

    data = json.load(sys.stdin)
    if set(data) != {"capture", "center", "cpu"} or os.sched_getaffinity(0) != {data["cpu"]}:
        raise ValueError("signed range child needs authenticated capture and fixed affinity")
    cap = data["capture"]
    if cap["catalog_timestamp_ns"] > cap["cutoff_utc_ns"]:
        raise ValueError("future orbit snapshot")
    capture = SimpleNamespace(**(cap | {"catalog": cap["catalog"].encode("ascii")}))
    output = code_carrier.evaluate(capture, data["center"])
    output.update(
        worker_s=perf_counter() - start,
        cpu_s=process_time() - cpu,
        peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
    )
    print(json.dumps(output, allow_nan=False))


def attempt(work, case, cpu):
    payload = encoded(dict(capture=native(case, work), center=case["center"], cpu=cpu))
    start = perf_counter()
    try:
        proc = subprocess.run(
            ["taskset", "-c", str(cpu), sys.executable, "-B", "-m", MODULE, "worker"],
            env=os.environ | THREAD_ENV,
            input=payload,
            capture_output=True,
            check=True,
            timeout=CAP,
        )
        result = json.loads(proc.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        detail = (getattr(error, "stderr", None) or b"").decode(errors="replace")[-2300:]
        status = "timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed"
        result = dict(status=status, reason=detail or str(error))
    out = dict(
        case,
        cpu=cpu,
        direct_wall_s=perf_counter() - start,
        input_sha256=sha256(payload).hexdigest(),
        **result,
    )
    save_json(work / f"{out['id']}-result.json", out)
    print(
        out["id"],
        out["status"],
        out.get("held_intervals"),
        round(out["direct_wall_s"], 2),
        out.get("reason", ""),
        flush=True,
    )
    return out


def run(work, report):
    if (report / LOCK).is_file():
        raise FileExistsError("the signed range predictions are already sealed")
    plan = whole_iq.read(whole_iq.checked(report / PLAN, (work / "plan.sha256").read_text()))
    for name, digest in plan["sources"].items():
        whole_iq.checked(Path(name), digest)

    def lane(i):
        return [attempt(work, case, CPUS[i]) for case in plan["cases"][i :: len(CPUS)]]

    with ThreadPoolExecutor(max_workers=len(CPUS)) as pool:
        rows = {row["id"]: row for group in pool.map(lane, range(len(CPUS))) for row in group}
    for name, digest in plan["sources"].items():
        whole_iq.checked(Path(name), digest)
    ids = [case["id"] for case in plan["cases"]]
    write(
        report / PREDICTIONS,
        gzip.compress(b"".join(encoded(rows[k]) + b"\n" for k in ids), mtime=0),
    )
    save_json(
        report / LOCK, dict(cases=ids, files={k: _sha(report / k) for k in (PLAN, PREDICTIONS)})
    )


def main():
    if sys.argv[1:] == ["worker"]:
        return worker()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "run"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("--report", type=local_output, default=OUT)
    parser.add_argument("--simulation-seed-file", type=Path)
    args = parser.parse_args()
    if args.action == "stage":
        return stage(args.work, args.report, args.simulation_seed_file)
    return run(args.work, args.report)


if __name__ == "__main__":
    main()
