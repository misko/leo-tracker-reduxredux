"""Export the checked receiver's verified factors and test the two v5 position solvers."""

import argparse
import ctypes as ct
import json
import os
import subprocess
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from time import perf_counter, process_time

import numpy as np

from .. import corpus
from ..scoring import distance_km
from ..variants.carrier_continuation import Continuation
from . import recording_to_v5
from .checked_scan_trial import CHECK
from .full_v5_check import _load_case, _probe, _sha, factor_candidate
from .reverse_glrt_reference import ARMS, CASES, packed, read_bound
from .reverse_glrt_report import read, write_csv
from .single_scan_roster import OUT, PRIOR, WORK
from .single_scan_trial import Native
from .timing_first_position import raw_windows
from .timing_first_report import tab
from .two_carrier_compact import compact
from .two_carrier_position import solve, write_native
from .two_carrier_roster import WORK as PRIOR_WORK

MODE = "checked_with_support"
ROOT = WORK / "full-recordings"
TRACE = Path(__file__).with_name("single_scan_factor_trace.c")


class Factor(ct.Structure):
    _fields_ = [("rank", ct.c_int), ("integer", ct.c_int)] + [
        (k, ct.c_double) for k in ("offset", "hz", "exact", "control")
    ]


def build():
    cmd = read(OUT / "builds.json")["builds"]["single_scan-x86-64"]["command"][:-2]
    at = cmd.index("-lm")
    cmd[at:at] = [str(TRACE), str(CHECK), "-Wl,--wrap=portable_verifier_glrt"]
    path = WORK / "bin" / "checked-scan-factors.so"
    cmd += ["-o", str(path)]
    subprocess.run(cmd, check=True)
    lock = dict(
        binary=_sha(path),
        command=cmd,
        base=_sha(OUT / "builds.json"),
        checked=_sha(OUT / "checked-build.json"),
        trace_source=_sha(TRACE),
        driver=_sha(Path(__file__)),
        protocol=_sha(OUT / "POSITION.md"),
    )
    dest = OUT / "position-build.json"
    if dest.exists() and read(dest) != lock:
        raise ValueError("position exporter changed")
    dest.write_bytes(packed(lock) + b"\n")


def acquire(job):
    case_id, cpu = job
    os.sched_setaffinity(0, {cpu})
    case = _load_case(case_id)
    lock = read(OUT / "position-build.json")
    binary = WORK / "bin/checked-scan-factors.so"
    if _sha(binary) != lock["binary"]:
        raise ValueError("position exporter binary changed")
    folder = ROOT / "captures" / case_id
    folder.mkdir(parents=True, exist_ok=True)
    receipt = folder / "capture.json"
    if receipt.exists():
        old = read(receipt)
        if (
            old["sources"] != lock
            or _sha(ROOT / MODE / case_id / "native.json") != old["inputs"][MODE]["native_sha256"]
        ):
            raise ValueError("existing whole-recording factors changed")
        return case_id, old["counts"]
    doc = read_bound(case["native"])
    previous = read(PRIOR_WORK / "captures" / case_id / "capture.json")
    original = {(r["visit_index"], r["receiver_id"]): r for r in doc["source"].pop("probes")}
    edge = next(iter(original.values()))["edge"]
    exclusions = {p["visit"]: p for p in doc["provenance"]["excluded_windows"]}
    signed, rows = [], []
    counts = Counter()
    policy = Continuation()
    asset = np.fromfile(PRIOR_WORK / "embedded" / (edge + ".f32"), dtype="<f4")
    r = Native(binary, asset)
    template = np.ascontiguousarray(asset[-80000:])
    numerical = r.lib.single_scan_factors
    numerical.argtypes = [
        ct.c_void_p,
        ct.c_void_p,
        ct.c_int,
        ct.c_double,
        ct.c_double,
        ct.c_void_p,
        ct.POINTER(Factor),
    ]
    begin, c0 = perf_counter(), process_time()
    try:
        for visit, w in enumerate(raw_windows(case)):
            acq = w.acquisition
            tune = json.loads(acq["retune_receipt"])
            if (
                acq["global_visit"] != visit
                or w.target["edge"] != edge
                or tuple(w.receiver_ids) != (0, 1)
                or w.sample_rate_hz != 10000000
                or any(
                    doc["delivery_clocks"][visit].get(k) != v
                    for k, v in tune["host_delivery_clock"].items()
                )
                or (visit == 0 and tune["utc_clock_bracket"] != doc["clock_anchor"])
            ):
                raise ValueError("timing or antenna identity changed")
            signed.append(w.iq_sha256)
            if visit in exclusions:
                e = exclusions[visit]
                if e["iq_sha256"] != w.iq_sha256 or e["sample_start"] != acq["sample_start"]:
                    raise ValueError("quality-excluded samples changed")
                continue
            if acq["quality_flags"] or not acq["complete"] or w.samples.shape != (200000, 2, 2):
                raise ValueError("invalid complete raw sample window")
            mid = w.target["rf_center_hz"] - w.target["lnb_lo_hz"] - acq["actual_if_center_hz"]
            for lane in (0, 1):
                vec = (Factor * 2)()
                n = numerical(
                    r.ctx,
                    w.samples.ctypes.data,
                    lane,
                    mid - 800000,
                    mid + 800000,
                    template.ctypes.data,
                    vec,
                )
                if not 0 <= n <= 2:
                    raise ValueError("native fractional scores differ from acquisition output")
                candidates = [
                    factor_candidate(
                        v.rank,
                        v.integer,
                        status="complete",
                        offset=v.offset,
                        cfo=v.hz,
                        exact=v.exact,
                        control=v.control,
                        margin=v.exact - v.control,
                    )
                    for v in vec[:n]
                ]
                if any(not v["passed_fractional_margin_gate"] for v in candidates):
                    raise ValueError("ungated output factor")
                p = _probe(w, lane, candidates)
                orig = original.pop((visit, lane))
                if any(orig[k] != v for k, v in p.items() if k != "candidates"):
                    raise ValueError("native visit metadata changed")
                _, keep, _ = policy.select(p)
                rows.append(dict(p, candidates=[] if keep is None else [candidates[keep]]))
                counts.update(
                    dict(probes=1, verified=n, two=int(n == 2), admitted=int(keep is not None))
                )
    finally:
        r.close()
    authority = recording_to_v5.digest([doc["source"]["input_manifest_sha256"], signed])
    if (
        original
        or authority != previous["raw_authority"]
        or len(signed) != previous["recorded_visits"]
        or counts["probes"] != previous["counts"]["probes"]
    ):
        raise ValueError("whole recording traversal differs from previous audited capture")
    inf = write_native(ROOT, doc, case_id, MODE, rows, authority, case["native"]["sha256"], lock)
    recording_to_v5.save(
        receipt,
        dict(
            case=case_id,
            inputs={MODE: inf},
            raw_authority=authority,
            counts=counts,
            real_visits=len(signed),
            excluded=len(exclusions),
            sources=lock,
            replay_wall_s=perf_counter() - begin,
            replay_cpu_s=process_time() - c0,
        ),
    )
    return case_id, dict(counts)


def evaluate(job):
    case, which, cpu = job
    if which == "original":
        return solve((case, MODE, cpu, ROOT))
    compact((case, MODE, cpu, ROOT))
    return case, which


def score():
    prev = tab(PRIOR / "positions.csv")
    truth = {r["id"]: r["truth"] for r in corpus.references("ds26-all159")}
    result = []
    for case in CASES:
        for solver in ("original", "compact"):
            path = (
                ROOT / MODE / case if solver == "original" else ROOT / "compact" / MODE / case
            ) / "prediction.json"
            p = read(path)
            for arm in ARMS:
                row = next(
                    r
                    for r in prev
                    if r["case"] == case
                    and r["solver"] == solver + "_v5"
                    and r["method"] == "original"
                    and r["arm"] == arm
                )
                info = p["arms"][arm]
                point = info.get("latlon") if p["status"] == "ok" else None
                result.append(
                    dict(
                        case=case,
                        solver=solver,
                        arm=arm,
                        status=p["status"],
                        reason=p.get("reason"),
                        original_error_km=row["error_km"],
                        checked_error_km=distance_km(point, truth[case]) if point else None,
                        original_rf_rms_hz=row["rf_rms_hz"],
                        checked_rf_rms_hz=info.get("rf_rms_hz"),
                        prediction_sha256=_sha(path),
                    )
                )
    write_csv(OUT / "replacement-positions.csv", result)
    capture = {c: read(ROOT / "captures" / c / "capture.json") for c in CASES}
    (OUT / "replacement-factors.json").write_bytes(packed(capture) + b"\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("build", "acquire", "solve", "score"))
    a = p.parse_args()
    if a.action == "build":
        build()
    elif a.action == "score":
        score()
    elif a.action == "acquire":
        with ProcessPoolExecutor(max_workers=5) as pool:
            for v in pool.map(acquire, zip(CASES, (0, 2, 4, 6, 7), strict=True)):
                print(v, flush=True)
    else:
        jobs = [
            (c, method, cpus[i])
            for method, cpus in (("compact", (8, 10, 12, 14, 16)), ("original", (0, 2, 4, 6, 7)))
            for i, c in enumerate(CASES)
        ]
        with ProcessPoolExecutor(max_workers=10) as pool:
            for v in pool.map(evaluate, jobs):
                print(v, flush=True)
