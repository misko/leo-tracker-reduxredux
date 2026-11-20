"""Replay inside and independently validated neighboring-region hypotheses."""

import argparse
import gzip
import hashlib
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, local_output, references, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants import region_challenge
from .cold_input import load, matched_offers
from .cold_missing import bindings
from .joint_pass_trials import MODES, ROSTER
from .joint_pass_trials import REPORT as INCUMBENT
from .joint_pass_trials import WORKER as JOINT_WORKER
from .joint_pass_trials import namespace as base_namespace
from .joint_pass_trials import source_digests as base_digests
from .prefix_figures import csv_file

REPORT = ROOT / "reports/2026_11_19_receiver_convergence/region-challenge"
WORKER = Path(__file__).with_name("region_challenge_worker.py")
DEADLINE_S = 100


def digests():
    known = base_digests()
    known.pop("joint_pass_worker.py")
    for path in (Path(region_challenge.__file__), WORKER):
        known[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return known


def namespace(cpu):
    command = base_namespace(cpu)
    command[command.index(str(JOINT_WORKER))] = str(WORKER)
    source = Path(region_challenge.__file__)
    command[-3:-3] = [
        "--ro-bind",
        str(source),
        f"/worker/tools/pipeline_eval/variants/{source.name}",
    ]
    return command


def trial(case, capture, mode, offer, binding, cpu, scratch, sources):
    raw = vars(capture).copy()
    raw["catalog"] = capture.catalog.decode("ascii")
    packet = encoded(dict(capture=raw, offer=offer))
    start = perf_counter()
    try:
        process = subprocess.run(
            namespace(cpu),
            input=packet,
            capture_output=True,
            cwd=scratch,
            timeout=DEADLINE_S,
            check=True,
        )
        result = json.loads(process.stdout)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
        result = dict(
            status="timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed",
            reason=(error.stderr or b"").decode(errors="replace")[-1600:] or str(error),
            boundary=region_challenge.BOUNDARY,
            metrics={},
            arms={a: {"latlon": None, "forced_latlon": None} for a in ARMS},
        )
    validate_result(result)
    row = dict(
        id=case,
        mode=mode,
        method=region_challenge.METHOD,
        result=result,
        offer=offer,
        cpu=cpu,
        worker_wall_s=perf_counter() - start,
        implementation_sha256=sources["region_challenge.py"],
        native_sha256=capture.native_sha256,
        catalog_sha256=capture.catalog_sha256,
        input_sha256=hashlib.sha256(packet).hexdigest(),
        **binding,
    )
    save_json(scratch / f"{case}-{mode}.json", row)
    print(case, mode, result["status"], round(row["worker_wall_s"], 2), flush=True)
    return row


def archive_jobs():
    omitted = {r["id"]: r for r in bindings()}
    jobs = []
    for case in ROSTER:
        capture = load(case)
        (tile,) = matched_offers(case)
        jobs.append((case, capture, MODES[0], dict(tile, width_km=tile.get("width_km", 25.0)), {}))
        if case in omitted:
            bound = omitted[case]
            if (capture.native_sha256, capture.catalog_sha256) != (
                bound["native_sha256"],
                bound["catalog_sha256"],
            ):
                raise ValueError("matched and omitted input capture/catalogue must agree")
            provenance = {k: bound[k] for k in ("query_id", "query_sha256", "supplied_offer_index")}
            jobs.append((case, capture, MODES[1], bound["supplied_tile"], provenance))
    return jobs


def replay(scratch, report, cpus):
    if len(cpus) != 2 or len(set(cpus)) != 2 or not set(cpus) <= os.sched_getaffinity(0):
        raise ValueError("choose two distinct available worker CPUs")
    sources = digests()
    jobs = archive_jobs()
    save_json(scratch / "source-lock.json", sources)

    def series(cpu, entries):
        return [trial(*entry, cpu, scratch, sources) for entry in entries]

    with ThreadPoolExecutor(max_workers=2) as pool:
        workers = [pool.submit(series, cpu, jobs[i::2]) for i, cpu in enumerate(cpus)]
        results = {(r["id"], r["mode"]): r for batch in workers for r in batch.result()}
    if sources != digests():
        raise ValueError("the locked method changed while the trial was running")
    for mode in MODES:
        rows = [results[case, mode] for case in ROSTER if (case, mode) in results]
        write(
            report / f"{mode}.jsonl.gz",
            gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0),
        )
    save_json(report / "source-lock.json", sources)


def passes_native_gate(result, arm):
    """Evaluate the preregistered validation gates without the outside comparison."""
    regions = result["metrics"].get("regions")
    if not regions:
        return False
    inside = regions[0]
    state = result["arms"][arm]
    rms = state.get("conditional_rms_hz")
    frame = state.get("heldout_frame_rms_us")
    return (
        inside["labels"] >= 4
        and inside["channels"] >= 2
        and inside["time_bins"] >= 3
        and state.get("validation_probes", 0) >= 12
        and state.get("validation_blocks", 0) >= 4
        and rms is not None
        and rms <= 500
        and state["heldout_within_450_fraction"] >= 0.7
        and (frame is None or frame <= 12)
        and not state["near_tile_edge"]
    )


def score(report):
    refs = {
        r["id"]: r
        for panel, prefix in (("ds26-common127", "DS26"), ("roof16", "DS29"))
        for r in references(panel, [case for case in ROSTER if case.startswith(prefix)])[1]
    }
    location, frequency, summary = [], [], {}
    for mode in MODES:
        with gzip.open(report / f"{mode}.jsonl.gz", "rt") as stream:
            rows = list(map(json.loads, stream))
        with gzip.open(INCUMBENT / f"{mode}.jsonl.gz", "rt") as stream:
            previous = {r["id"]: r for r in map(json.loads, stream)}
        expected = ROSTER if mode == MODES[0] else ROSTER[3:]
        if tuple(r["id"] for r in rows) != expected or any(r["mode"] != mode for r in rows):
            raise ValueError("prediction roster differs from the declared trial")
        pos, rf = [], []
        for row in rows:
            case, result = row["id"], row["result"]
            base = previous[case]
            if any(row[k] != base[k] for k in ("offer", "native_sha256", "catalog_sha256")):
                raise ValueError("incumbent inputs differ from the challenger inputs")
            truth = refs[case]["truth"]
            for arm in ARMS:
                state, control = result["arms"][arm], base["result"]["arms"][arm]
                pos.append(
                    dict(
                        id=case,
                        mode=mode,
                        arm=arm,
                        status=result["status"],
                        returned_km=distance_km(state["latlon"], truth),
                        forced_km=distance_km(state["forced_latlon"], truth),
                        incumbent_returned_km=distance_km(control["latlon"], truth),
                        incumbent_forced_km=distance_km(control["forced_latlon"], truth),
                        original_v5_km=refs[case]["reference"]["baseline"][arm]["error_km"]
                        if mode == MODES[0]
                        else None,
                        worker_wall_s=row["worker_wall_s"],
                    )
                )
                rf.append(
                    dict(
                        id=case,
                        mode=mode,
                        arm=arm,
                        heldout_rms_hz=state.get("conditional_rms_hz"),
                        incumbent_tail_rms_hz=control.get("conditional_rms_hz"),
                        heldout_frame_rms_us=state.get("heldout_frame_rms_us"),
                        validation_margin=state.get("validation_margin"),
                        validation_log_odds=state.get("validation_log_odds"),
                        passes_native_gate=passes_native_gate(result, arm),
                    )
                )
        location.extend(pos)
        frequency.extend(rf)
        summary[mode] = dict(
            count=len(rows),
            arms={
                arm: dict(
                    returned_km=distribution(r["returned_km"] for r in pos if r["arm"] == arm),
                    forced_km=distribution(r["forced_km"] for r in pos if r["arm"] == arm),
                    incumbent_returned_km=distribution(
                        r["incumbent_returned_km"] for r in pos if r["arm"] == arm
                    ),
                    heldout_rms_hz=distribution(r["heldout_rms_hz"] for r in rf if r["arm"] == arm),
                    inside_only_eligible=sum(
                        r["passes_native_gate"] for r in rf if r["arm"] == arm
                    ),
                )
                for arm in ARMS
            },
            paired_fitted_minus_zero={
                key: distribution(
                    data[i + 1][key] - data[i][key]
                    for i in range(0, len(data), 2)
                    if data[i][key] is not None and data[i + 1][key] is not None
                )
                for key, data in (("forced_km", pos), ("heldout_rms_hz", rf))
            },
            worker_wall_s=distribution(r["worker_wall_s"] for r in rows),
        )
    csv_file(report / "position-errors.csv", location)
    csv_file(report / "conditional-frequency.csv", frequency)
    save_json(report / "summary.json", summary)


def score_fresh_gates(fresh, report):
    lock = json.loads((fresh / "prediction-lock.json").read_bytes())
    raw = (fresh / "predictions.jsonl.gz").read_bytes()
    if hashlib.sha256(raw).hexdigest() != lock["predictions_sha256"]:
        raise ValueError("fresh prediction bytes differ from the sealed synthetic comparison")
    predictions = {
        (r["cohort"], r["id"]): r["result"]
        for line in gzip.decompress(raw).splitlines()
        if (r := json.loads(line))["method"] == region_challenge.METHOD
    }
    source = json.loads((fresh / "scores.json").read_bytes())["cases"]
    rows = []
    for row in source:
        if row["method"] != region_challenge.METHOD:
            continue
        result = predictions[row["cohort"], row["id"]]
        arm = row["arm"]
        state = result["arms"][arm]
        if (state["latlon"] is not None) != row["published"]:
            raise ValueError("fresh score and released receiver decision disagree")
        rows.append(
            {
                **{k: row[k] for k in ("id", "cohort", "condition", "arm", "published")},
                "passes_native_gate": passes_native_gate(result, arm),
                "beats_every_outside": state.get("validation_margin", 0) > 0,
                "validation_margin": state.get("validation_margin"),
                "validation_log_odds": state.get("validation_log_odds"),
                "heldout_rms_hz": state.get("conditional_rms_hz"),
                "center_error_km": row["center_error_km"],
                "forced_error_km": row["forced_error_km"],
            }
        )
    csv_file(report / "fresh-gate-audit.csv", rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score", action="store_true")
    parser.add_argument("--fresh-report", type=Path)
    parser.add_argument("--scratch", type=Path, default=Path("/tmp/leo-region-challenge"))
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--cpus", type=int, nargs=2, default=(6, 7))
    args = parser.parse_args()
    scratch, report = local_output(args.scratch), local_output(args.report)
    scratch.mkdir(parents=True, exist_ok=True)
    if args.score:
        score(report)
    elif args.fresh_report:
        score_fresh_gates(args.fresh_report, report)
    else:
        replay(scratch, report, args.cpus)


if __name__ == "__main__":
    main()
