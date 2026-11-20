"""Freeze and run a matched held forecast of anonymous satellite carrier levels."""

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
from unittest.mock import patch

from .. import corpus, whole_iq
from ..__main__ import ROOT, THREAD_ENV, encoded, local_output, save_json, write
from . import cold_input, sequential_fix_trial
from .full_v5_check import _sha

OUT = sequential_fix_trial.SCREEN / "coarse-and-navigation/clock-transfer"
CPUS = (20, 21)
CAP = 90
MEMORY = 512 * 1024**2
MODULE = "tools.pipeline_eval.qualification.clock_transfer_grouped_trial"
PLAN = "blind-plan.json"
PRED = "predictions.jsonl.gz"
LOCK = "prediction-lock.json"
EXCLUDE = frozenset(("DS26-0002", "DS26-0030", "DS26-0058", "DS29-0082", "DS29-0127", "DS29-0174"))


def selection():
    inventory = sequential_fix_trial.inventory()
    rows, audit = [], {}
    spacing = 12 * 3600 * 10**9
    for panel in ("DS26", "DS29"):
        last = 0
        attempted = []
        for case in sorted(
            inventory.values(), key=lambda r: (r.get("cutoff_utc_ns") or 0, r["id"])
        ):
            if (
                case["panel"] != panel
                or case["id"] in EXCLUDE
                or not case["id"].startswith(panel)
                or not all(case.get(k) for k in ("native", "catalog", "regions", "cutoff_utc_ns"))
                or case["cutoff_utc_ns"] - last < spacing
            ):
                continue
            note = dict(id=case["id"], cutoff_utc_ns=case["cutoff_utc_ns"])
            attempted.append(note)
            try:
                capture = cold_input.load(note["id"])
                if not 295 <= capture.duration_s <= 305:
                    raise ValueError("requires complete five-minute support")
            except (OSError, KeyError, ValueError) as error:
                note["ineligible"] = str(error)
                continue
            rows.append(
                dict(
                    note,
                    group=panel,
                    center=case["regions"][0]["center"],
                    native_sha256=capture.native_sha256,
                    catalog_sha256=capture.catalog_sha256,
                    collected_utc_ns=capture.catalog_timestamp_ns,
                )
            )
            last = case["cutoff_utc_ns"]
            if sum(r["group"] == panel for r in rows) == 2:
                break
        audit[panel] = attempted
        if sum(r["group"] == panel for r in rows) != 2:
            raise ValueError(f"need two disjoint clock transfer acquisitions in {panel}")
    return rows, audit


def simulation(work, seed_file):
    import numpy as np

    from ..variants import peak_paths
    from ..variants.folded_doppler import _offset
    from . import cold_scenes
    from .site_transfer_samples import _catalogue

    private = work / "private"
    private.mkdir(mode=0o700)
    seed = secrets.token_bytes(32) if seed_file is None else seed_file.read_bytes()
    if len(seed) != 32:
        raise ValueError("the simulation seed requires 32 bytes")
    write(private / "seed.bin", seed)
    rng = np.random.default_rng(int.from_bytes(seed, "big"))
    center = (np.array([-20.0, 126.0]) + rng.uniform(-2.0, 2.0, 2)).tolist()
    truth = list(_offset(center, rng.uniform(4.0, 6.0), rng.uniform(-5.0, 5.0)))
    catalog, collected = _catalogue()
    start = collected + 5800 * 10**9
    orbits = cold_scenes._constellation(catalog, collected)
    emitters = cold_scenes._emitters

    def correlated(*args):
        by_block = {}
        return [(block, rf, by_block.setdefault(block, sat)) for block, rf, sat in emitters(*args)]

    with patch.object(cold_scenes, "_emitters", correlated):
        probes, counter, latent = cold_scenes._generate_capture(orbits, start, truth, rng)
    lookup, carrier = {}, {}
    for row in latent["emitters"]:
        sat = row["norad"]
        if sat not in carrier:
            carrier[sat] = float(rng.normal(0, 425))
        lookup[row["block"], row["channel"]] = sat, row["offset_hz"]
    for probe in probes:
        viable = [p for p in probe["candidates"] if p["passed_fractional_margin_gate"]]
        if viable:
            t = (probe["valid_start_counter"] - counter) / cold_scenes.RATE
            sat, old = lookup[int(t // 50), probe["channel"]]
            residual = carrier[sat] * probe["actual_rf_hz"] / 11.5e9
            for peak in viable:
                peak["fractional_tracking_cfo_hz"] = float(
                    peak_paths.fold(peak["fractional_tracking_cfo_hz"] - old + residual)
                )
    ident = rng.bytes(10).hex()
    doc = dict(
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
    native = work / "simulation.json.gz"
    write(native, gzip.compress(encoded(doc), mtime=0))
    write(work / "simulation.tle", catalog)
    labels = private / "labels.json"
    save_json(labels, dict(truth=truth, emitter=latent, scaled_carrier_hz=carrier))
    row = dict(
        id=ident,
        group="simulated",
        center=center,
        cutoff_utc_ns=start,
        collected_utc_ns=collected,
        native_sha256=_sha(native),
        catalog_sha256=_sha(work / "simulation.tle"),
    )
    return row, dict(labels_sha256=_sha(labels), seed_sha256=_sha(private / "seed.bin"))


def stage(work, report, *, seed_file=None):
    if (report / PLAN).is_file():
        raise FileExistsError("the clock-transfer roster already exists")
    real, audit = selection()
    work.mkdir(parents=True, mode=0o700)
    simulated, private = simulation(work, seed_file)
    source_names = (
        "tools/pipeline_eval/variants/clock_transfer_grouped.py",
        "tools/pipeline_eval/variants/absolute_doppler.py",
        "tools/pipeline_eval/variants/joint_pass.py",
        "tools/pipeline_eval/variants/peak_paths.py",
        "tools/pipeline_eval/variants/multi_session.py",
        "tools/pipeline_eval/reference/grid.py",
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
        *(ROOT / n for n in source_names),
    ]
    plan = dict(
        cases=[*real, simulated],
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


def worker():
    start, cpu = perf_counter(), process_time()
    setrlimit(RLIMIT_AS, (MEMORY, MEMORY))
    from ..variants import clock_transfer_grouped

    data = json.load(sys.stdin)
    if set(data) != {"capture", "center", "cpu"} or os.sched_getaffinity(0) != {data["cpu"]}:
        raise ValueError("clock transfer worker has incorrect input or affinity")
    cap = data["capture"]
    if cap["catalog_timestamp_ns"] > cap["cutoff_utc_ns"]:
        raise ValueError("future orbit snapshot")
    capture = SimpleNamespace(**(cap | {"catalog": cap["catalog"].encode("ascii")}))
    result = clock_transfer_grouped.evaluate(capture, data["center"])
    result.update(
        worker_s=perf_counter() - start,
        worker_cpu_s=process_time() - cpu,
        peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
    )
    print(json.dumps(result, allow_nan=False))


def native(case, work):
    if case["group"] == "simulated":
        raw = whole_iq.checked(work / "simulation.json.gz", case["native_sha256"])
        catalog = whole_iq.checked(work / "simulation.tle", case["catalog_sha256"])
        return json.loads(gzip.decompress(raw.read_bytes())) | {"catalog": catalog.read_text()}
    cap = cold_input.load(case["id"])
    if (cap.native_sha256, cap.catalog_sha256, cap.cutoff_utc_ns, cap.catalog_timestamp_ns) != (
        case["native_sha256"],
        case["catalog_sha256"],
        case["cutoff_utc_ns"],
        case["collected_utc_ns"],
    ):
        raise ValueError("original GLRT or causal authority changed")
    return vars(cap) | {"catalog": cap.catalog.decode("ascii")}


def attempt(work, case, cpu):
    payload = encoded(dict(capture=native(case, work), center=case["center"], cpu=cpu))
    started = perf_counter()
    try:
        proc = subprocess.run(
            ["taskset", "-c", str(cpu), sys.executable, "-B", "-m", MODULE, "worker"],
            env=os.environ | THREAD_ENV,
            input=payload,
            capture_output=True,
            check=True,
            timeout=CAP,
        )
        outcome = json.loads(proc.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        detail = (getattr(error, "stderr", None) or b"").decode(errors="replace")[-2500:]
        status = "timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed"
        outcome = dict(status=status, reason=detail or str(error))
    row = dict(
        case,
        cpu=cpu,
        input_sha256=sha256(payload).hexdigest(),
        direct_worker_s=perf_counter() - started,
        **outcome,
    )
    save_json(work / f"{case['id']}-result.json", row)
    print(
        case["id"],
        row["status"],
        round(row["direct_worker_s"], 2),
        row.get("reason", ""),
        row.get("audit"),
        flush=True,
    )
    return row


def run(work, report):
    if (report / LOCK).exists():
        raise FileExistsError("the clock-transfer predictions are already sealed")
    plan = whole_iq.read(whole_iq.checked(report / PLAN, (work / "plan.sha256").read_text()))
    for name, digest in plan["sources"].items():
        whole_iq.checked(Path(name), digest)

    def lane(i):
        return [attempt(work, case, CPUS[i]) for case in plan["cases"][i :: len(CPUS)]]

    with ThreadPoolExecutor(max_workers=len(CPUS)) as pool:
        rows = {r["id"]: r for group in pool.map(lane, range(len(CPUS))) for r in group}
    for name, digest in plan["sources"].items():
        whole_iq.checked(Path(name), digest)
    ids = [case["id"] for case in plan["cases"]]
    write(report / PRED, gzip.compress(b"".join(encoded(rows[k]) + b"\n" for k in ids), mtime=0))
    save_json(report / LOCK, dict(cases=ids, files={n: _sha(report / n) for n in (PLAN, PRED)}))


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
        return stage(args.work, args.report, seed_file=args.simulation_seed_file)
    return run(args.work, args.report)


if __name__ == "__main__":
    main()
