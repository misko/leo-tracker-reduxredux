"""Replay the guarded track receiver and unchanged controls on eight new roof cases."""

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
from ..__main__ import ROOT, encoded, local_output, references, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants import robust_em, robust_orbit_fit, robust_support
from . import robust_orbit_fit_trials as old
from .prefix_figures import csv_file
from .robust_em_trials import load

REPORT = ROOT / "reports/2026_11_19_receiver_screening/lean-support"
WORKER = Path(__file__).with_name("lean_support_worker.py")
OFFERS = corpus.FROZEN / "roof-four-offers.json"
METHODS = (robust_em.METHOD, robust_orbit_fit.METHOD, robust_support.METHOD)
ROOF = (
    "DS29-0357",
    "DS29-0604",
    "DS26-0277",
    "DS29-0316",
    "DS29-0127",
    "DS26-0209",
    "DS26-0203",
    "DS26-0070",
)
MODES = ("matched-tile", "wrong-region")
CAP = 45
ARCHIVE = "predictions.jsonl.gz"


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def source_lock():
    parents = old.locked_sources()
    if parents != json.loads((old.OUTPUT / "source-lock.json").read_bytes()):
        raise ValueError("original lean or exact geometry control differs from locked sources")
    selected = set(corpus._selection("roof16")[0]) - set(old.TIMING_IDS) - set(old.CONFIRMATION)
    roster = tuple(
        sorted(selected, key=lambda c: sha256(("lean-support/roof/v1:" + c).encode()).digest())[:8]
    )
    if roster != ROOF:
        raise ValueError("frozen roof cohort changed")
    return dict(
        files=dict(
            parents,
            **{p.name: digest(p) for p in (Path(robust_support.__file__), WORKER, Path(__file__))},
        ),
        offers_sha256=digest(OFFERS),
        cases=list(ROOF),
        modes=list(MODES),
        cap_wall_s=CAP,
    )


def wrong_offer(original, manifest):
    choices = sorted(
        (distance_km(r["center"], original["center"]), r["id"], r)
        for r in manifest
        if r["id"] != original["id"]
    )
    return next(r for separation, _, r in choices if separation > 25 * 2**0.5)


def command(cpu, method):
    args = old.command(cpu, method)
    args[args.index(str(old.TRIAL_WORKER))] = str(WORKER)
    candidate = Path(robust_support.__file__)
    args[-4:-4] = [
        "--ro-bind",
        str(candidate),
        f"/worker/tools/pipeline_eval/variants/{candidate.name}",
    ]
    return args


def run_one(case, mode, method, packet, bindings, cpu, source):
    raw = encoded(packet)
    started = perf_counter()
    try:
        out = json.loads(
            subprocess.run(
                command(cpu, method), input=raw, capture_output=True, check=True, timeout=CAP
            ).stdout
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        out = dict(
            worker_cpu_s=None,
            max_rss_kib=None,
            result=dict(
                status="timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed",
                reason=(error.stderr or b"").decode(errors="replace")[-2500:] or str(error),
                arms={arm: {"latlon": None} for arm in ARMS},
                metrics={},
                boundary="anonymous GLRT and causal catalogue to one-tile position",
            ),
        )
    wall = perf_counter() - started
    validate_result(out["result"])
    print(case, mode, method, out["result"]["status"], round(wall, 2), flush=True)
    return dict(
        id=case,
        mode=mode,
        method=method,
        tile=packet["offer"],
        cpu=cpu,
        worker_wall_s=wall,
        input_sha256=sha256(raw).hexdigest(),
        implementation_sha256=source["files"][method + ".py"],
        **bindings,
        **out,
    )


def trial(report, cache, cpus):
    seal = json.loads((report / "source-lock.json").read_bytes())
    if seal != source_lock():
        raise ValueError("study source differs from pre-input lock")
    offers = json.loads(OFFERS.read_bytes())

    def lane(slot):
        rows = []
        for index in range(slot, len(ROOF), 2):
            case = ROOF[index]
            packet, bindings = load(case, "matched-tile", cache)
            original = packet["offer"]
            manifest = offers[case]
            if any(manifest[k] != bindings[k] for k in ("observation_sha256", "catalog_sha256")):
                raise ValueError("four-tile archive has different observation/catalogue")
            wrong = wrong_offer(original, manifest["regions"])
            order = METHODS[index % 3 :] + METHODS[: index % 3]
            for mode, tile, sequence in zip(
                MODES, (original, wrong), (order, order[::-1]), strict=True
            ):
                for method in sequence:
                    rows.append(
                        run_one(
                            case, mode, method, dict(packet, offer=tile), bindings, cpus[slot], seal
                        )
                    )
        return rows

    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = [r for results in pool.map(lane, range(2)) for r in results]
    if seal != source_lock():
        raise ValueError("study source changed during predictions")
    rows.sort(
        key=lambda r: (ROOF.index(r["id"]), MODES.index(r["mode"]), METHODS.index(r["method"]))
    )
    for start in range(0, len(rows), len(METHODS)):
        pair = rows[start : start + len(METHODS)]
        if not all(
            len({encoded(r[k]) for r in pair}) == 1
            for k in (
                "id",
                "mode",
                "input_sha256",
                "tile",
                "native_sha256",
                "catalog_sha256",
                "observation_sha256",
            )
        ):
            raise ValueError("fitter inputs differ within an offered tile")
    write(report / ARCHIVE, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))
    save_json(
        report / "prediction-lock.json",
        dict(
            files={ARCHIVE: digest(report / ARCHIVE)},
            cases=list(ROOF),
            methods=list(METHODS),
            modes=list(MODES),
            source_lock_sha256=digest(report / "source-lock.json"),
        ),
    )


def score(report):
    lock = json.loads((report / "prediction-lock.json").read_bytes())
    packet = (report / ARCHIVE).read_bytes()
    if (
        sha256(packet).hexdigest() != lock["files"][ARCHIVE]
        or digest(report / "source-lock.json") != lock["source_lock_sha256"]
    ):
        raise ValueError("read only sealed result and source receipts")
    predictions = list(map(json.loads, gzip.decompress(packet).splitlines()))
    if len(predictions) != len(ROOF) * len(MODES) * len(METHODS):
        raise ValueError("incomplete prediction inventory")
    truth = {row["id"]: row["truth"] for row in references("roof16", ROOF)[1]}
    queries, rows = {}, []
    for p in predictions:
        site = truth[p["id"]]
        if p["mode"] == "wrong-region":
            center_error = distance_km(site, p["tile"]["center"])
            if center_error <= float(p["tile"].get("width_km", 25)) / 2**0.5:
                raise ValueError("wrong offer could include the reference location")
            queries[p["id"]] = dict(offer=p["tile"], truth=site, center_error_km=center_error)
        r = p["result"]
        for arm in ARMS:
            a = r["arms"][arm]
            rows.append(
                dict(
                    id=p["id"],
                    mode=p["mode"],
                    method=p["method"],
                    arm=arm,
                    status=r["status"],
                    reason=r["reason"],
                    error_km=distance_km(a["latlon"], site),
                    forced_error_km=distance_km(a.get("forced_latlon"), site),
                    conditional_rms_hz=a.get("rf_rms_hz"),
                    fit_score=a.get("frequency_score"),
                    rss_kib=p["max_rss_kib"],
                    cpu_s=p["worker_cpu_s"],
                    wall_s=p["worker_wall_s"],
                )
            )
    csv_file(report / "scores.csv", rows)
    save_json(report / "wrong-offers.json", queries)
    all_common = {
        c
        for c in ROOF
        if sum(r["id"] == c and r["mode"] == MODES[0] and r["status"] == "ok" for r in rows)
        == len(METHODS) * len(ARMS)
    }
    summary = []
    for method in METHODS:
        for mode in MODES:
            for arm in ARMS:
                selected = [
                    r for r in rows if (r["method"], r["mode"], r["arm"]) == (method, mode, arm)
                ]
                errors = [r["error_km"] for r in selected if r["error_km"] is not None]
                summary.append(
                    dict(
                        method=method,
                        mode=mode,
                        arm=arm,
                        cases=len(selected),
                        fixes=len(errors),
                        within_5km=sum(e <= 5 for e in errors),
                        issued=distribution(errors),
                        common_fixes=distribution(
                            r["error_km"]
                            for r in selected
                            if r["id"] in all_common and mode == MODES[0]
                        ),
                        rms=distribution(r["conditional_rms_hz"] for r in selected),
                        wall_s=distribution(r["wall_s"] for r in selected),
                        cpu_s=distribution(r["cpu_s"] for r in selected),
                        peak_rss_kib=max(
                            (r["rss_kib"] for r in selected if r["rss_kib"] is not None),
                            default=None,
                        ),
                    )
                )
    save_json(report / "summary.json", summary)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("seal", "trial", "score"))
    p.add_argument("--report", type=local_output, default=REPORT)
    p.add_argument("--cache", type=local_output, required=True)
    p.add_argument("--cpus", type=int, nargs=2, default=(10, 11))
    args = p.parse_args()
    if args.action == "seal":
        path = args.report / "source-lock.json"
        seal = source_lock()
        if path.exists() and json.loads(path.read_bytes()) != seal:
            raise ValueError("refuse to replace existing source lock")
        if not path.exists():
            save_json(path, seal)
    elif args.action == "trial":
        if len(set(args.cpus)) != 2 or not set(args.cpus) <= os.sched_getaffinity(0):
            p.error("choose two available distinct CPU pins")
        trial(args.report, args.cache, args.cpus)
    else:
        score(args.report)


if __name__ == "__main__":
    main()
