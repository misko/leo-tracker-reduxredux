"""Stage the measured cross-satellite phase cohort and isolate the orbit searches."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy.io import loadmat

from ..__main__ import ROOT, encoded, save_json
from ..scoring import ARMS, validate_result
from ..variants import array_closure as model
from . import bearing_transfer_trial as prior
from .armijo_finish_results import pack
from .physical_differences import consolidate, simultaneous

OUT = ROOT / "reports/2026_11_19_receiver_screening/coarse-and-navigation/array-closure"
CAP, CPU = prior.CAP, (18, 19)
ARCHIVE = "positions.jsonl.gz"
MATCH = ("native_sha256", "catalogue_sha256", "calibration_sha256", "endpoint_support_sha256")
WORKER = """
import json
import sys
from resource import RLIMIT_AS, RUSAGE_SELF, getrusage, setrlimit
from time import perf_counter, process_time

start, cpu = perf_counter(), process_time()
setrlimit(RLIMIT_AS, (640 << 20, 640 << 20))
from tools.pipeline_eval.variants import array_closure
q = json.load(sys.stdin)
assert set(q) == {'observation', 'catalogue', 'center', 'labels'}
value = array_closure.solve(**q)
json.dump(dict(results=value, worker_wall_s=perf_counter()-start, cpu_s=process_time()-cpu,
               rss_kib=getrusage(RUSAGE_SELF).ru_maxrss), sys.stdout, allow_nan=False)
"""


def source_support(data, calibration):
    mats = data["main_tone_dict"].ravel()
    names = [str(v.item()) for v in data["id_dict"].ravel()]
    if len(mats) != len(names) or any(m.shape[1] != 5 or not np.iscomplexobj(m) for m in mats):
        raise ValueError("expected published phases in three complex spectral columns")
    time = calibration["ref_sig_idx"][:, 0] / 2e6
    phase = np.column_stack(
        (
            -calibration["phase_offset_21"].ravel(),
            calibration["phase_offset_01"].ravel(),
        )
    )
    if len(time) < 2 or np.any(np.diff(time) <= 0) or not np.isfinite(phase).all():
        raise ValueError("invalid ordered calibration reference samples")
    raw = [consolidate(a) for a in mats]
    _, pair_audit = simultaneous(raw)
    drop = {
        min(r["track_rows"], key=lambda i: (np.ptp(raw[i][0]), -i))
        for r in pair_audit
        if r["harmonic_like"]
    }
    support, available = model.support(mats, drop, (time, np.unwrap(phase, axis=0)))
    ledger = dict(
        fft_rows=sum(len(x) for x in mats),
        released_arcs=len(mats),
        potential_copy_arcs=sorted(drop),
        references=len(time),
        exact_candidates=available,
        scopes=support,
    )
    return ledger, names


def stage(raw, calibration):
    prior_lock = prior.OUT / "prediction-lock.json"
    evidence = prior.read(prior_lock)
    for p, h in evidence["files"].items():
        if prior.digest((prior.OUT / p).read_bytes()) != h:
            raise ValueError("paired offer or data authority changed")
    previous = prior.read(prior.OUT / "blind-plan.json")
    inventory = {
        q["native_sha256"]: q
        for q in prior.read(prior.OUT / "measurement-inventory.json")["captures"]
    }
    study = prior.authority.STUDY
    public = study / "public_field"
    receipt = prior.read(study / "field-receipt.json")
    cache, jobs, observed = {}, [], []
    for old in previous["cases"]:
        sha = old["native_sha256"]
        if sha not in cache:
            entry = inventory[sha]
            date = entry["date"]
            ref = entry["hardware_only_calibration"]["calibration_sha256"]
            raw_mat = prior.authority._read(raw / date / "tracked_tones.mat", sha)
            cal_mat = prior.authority._read(calibration / f"{date}-calibration.mat", ref)
            ledger, labels = source_support(loadmat(BytesIO(raw_mat)), loadmat(BytesIO(cal_mat)))
            ident = old["original_case_id"]
            q = json.loads(
                prior.authority._read(
                    public / "queries" / f"{ident}.json",
                    receipt["public_query_sha256"][ident],
                )
            )
            catalog = prior.authority._read(
                public / "orbits" / f"{q['catalog']}.tle",
                q["catalog"],
            ).decode("ascii")
            meta = json.loads(
                prior.authority._read(
                    public / "observations" / f"{q['observation']}.json",
                    q["observation"],
                )
            )
            clock = {
                k: meta[k]
                for k in ("anchor_utc_ns", "cutoff_utc_ns", "catalog_timestamp_ns", "duration_s")
            }
            if q["catalog"] != old["catalogue_sha256"] or (
                clock["catalog_timestamp_ns"] > clock["cutoff_utc_ns"]
            ):
                raise ValueError("invalid causal or matched orbit authority")
            cache[sha] = (dict(clock=clock, groups=ledger["scopes"]), labels, catalog, ref)
            observed.append(
                dict(
                    id=entry["id"],
                    date=date,
                    native_sha256=sha,
                    calibration_sha256=ref,
                    **ledger,
                )
            )
        measured, labels, catalog, ref = cache[sha]
        capture = dict(
            observation=measured,
            catalogue=catalog,
            center=old["tile"]["center"],
            labels=labels if old["author_id"] else None,
        )
        payload = encoded(capture)
        binding = {
            k: old[k]
            for k in (
                "id",
                "mode",
                "author_id",
                "site",
                "repeat",
                "original_case_id",
                "tile",
                "native_sha256",
                "catalogue_sha256",
            )
        }
        binding.update(
            calibration_sha256=ref,
            endpoint_support_sha256=prior.digest(encoded(measured)),
            input_sha256=prior.digest(payload),
        )
        jobs.append((binding, payload))
    if len(observed) != 11 or len(jobs) != 44:
        raise ValueError("expected the frozen eleven-capture and two-offer cohort")
    return jobs, observed, prior_lock, previous["scoring_truth_sha256"]


def command(cpu):
    argv = prior.command(cpu)
    path = Path(model.__file__)
    argv[-4:-4] = ["--ro-bind", str(path), str(Path("/worker") / path.relative_to(ROOT))]
    argv[-1] = WORKER
    return argv


def names(assisted):
    suffix = "_author_id" if assisted else ""
    return [
        (f"{s}_{m}", "array_closure_" + s + "_" + m + suffix)
        for s in model.SCOPES
        for m in model.METHODS
    ]


def attempt(cpu, q, payload):
    start = perf_counter()
    try:
        p = subprocess.run(
            command(cpu),
            input=payload,
            capture_output=True,
            timeout=CAP,
            check=True,
        )
        row = json.loads(p.stdout)
    except (OSError, subprocess.SubprocessError) as e:
        detail = (getattr(e, "stderr", None) or b"").decode(errors="replace")[-1500:]
        fail = dict(
            status="timed_out" if isinstance(e, subprocess.TimeoutExpired) else "failed",
            reason=detail or str(e),
            boundary=model.BOUNDARY,
            metrics={},
            arms={a: dict(latlon=None, forced_latlon=None) for a in ARMS},
        )
        row = dict(results={k: fail for k, _ in names(q["author_id"])})
    elapsed = perf_counter() - start
    methods = row.pop("results")
    measurements = []
    for short, long in names(q["author_id"]):
        result = methods[short]
        validate_result(result)
        measurements.append(q | row | dict(method=long, result=result, elapsed_s=elapsed, cpu=cpu))
    print(
        q["id"],
        q["author_id"],
        methods["coincident_closure"]["status"],
        methods["coincident_closure"]["metrics"].get("modeled_pairs"),
        methods["wire_stable_closure"]["metrics"].get("modeled_pairs"),
        round(elapsed, 2),
        flush=True,
    )
    return measurements


def run(raw, calibration):
    cases, data, prior_lock, truth = stage(raw, calibration)
    sources = [
        *prior.sources(),
        Path(prior.__file__),
        Path(model.__file__),
        Path(__file__),
        OUT / "PROTOCOL.md",
        prior_lock,
        ROOT / "src/leo/sky/frames.py",
        ROOT / "src/leo/sky/propagation.py",
        Path(prior.__file__).with_name("physical_differences.py"),
    ]
    source_hashes = {str(p.relative_to(ROOT)): prior.digest(p.read_bytes()) for p in sources}
    save_json(OUT / "source-lock.json", source_hashes)
    save_json(
        OUT / "blind-plan.json",
        dict(cases=[q for q, _ in cases], scoring_truth_sha256=truth, deadline_s=CAP, cpus=CPU),
    )
    save_json(OUT / "paired-support.json", dict(captures=data))

    def lane(i):
        return [r for q, p in cases[i :: len(CPU)] for r in attempt(CPU[i], q, p)]

    with ThreadPoolExecutor(len(CPU)) as pool:
        rows = [r for lane_rows in pool.map(lane, range(len(CPU))) for r in lane_rows]
    if any(prior.digest((ROOT / k).read_bytes()) != v for k, v in source_hashes.items()):
        raise ValueError("a frozen program or protocol changed while running")
    artifacts = ("blind-plan.json", "source-lock.json", "paired-support.json")
    files = {n: prior.digest((OUT / n).read_bytes()) for n in artifacts}
    files[ARCHIVE] = pack(OUT, ARCHIVE, rows)
    save_json(OUT / "prediction-lock.json", dict(files=files, calls=len(cases)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("calibration", type=Path)
    args = parser.parse_args()
    run(args.raw, args.calibration)
