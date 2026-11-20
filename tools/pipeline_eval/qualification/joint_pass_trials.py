"""Evaluate native GLRT joint pass identity on archived offered and omitted regions."""

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
from ..variants import joint_pass_id, rate_triplets
from .cold_input import load, matched_offers
from .cold_missing import bindings
from .prefix_figures import csv_file
from .rate_triplet_trials import WORKER as SHARED_WORKER
from .rate_triplet_trials import sandbox_command

ROSTER = ("DS26-0036", "DS26-0122", "DS26-0237", "DS29-0082", "DS29-0174", "DS29-0247")
MODES = ("matched-tile", "omitted-tile")
REPORT = ROOT / "reports/2026_11_19_short_receiver/joint-pass"
WORKER = Path(__file__).with_name("joint_pass_worker.py")
DEADLINE_S = 90


def source_digests():
    paths = (Path(joint_pass_id.__file__), Path(rate_triplets.__file__), WORKER)
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def namespace(cpu):
    command = sandbox_command(cpu)
    command[command.index(str(SHARED_WORKER))] = str(WORKER)
    destination = "/worker/tools/pipeline_eval/variants"
    for module in (joint_pass_id, rate_triplets):
        source = Path(module.__file__)
        command[-3:-3] = ["--ro-bind", str(source), f"{destination}/{source.name}"]
    return command


def trial(case, capture, mode, offer, binding, cpu, scratch, sources):
    raw = vars(capture).copy()
    raw["catalog"] = capture.catalog.decode("ascii")
    data = encoded(dict(capture=raw, offer=offer))
    start = perf_counter()
    try:
        completed = subprocess.run(
            namespace(cpu),
            input=data,
            capture_output=True,
            cwd=scratch,
            timeout=DEADLINE_S,
            check=True,
        )
        result = json.loads(completed.stdout)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
        result = dict(
            status="timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed",
            reason=(error.stderr or b"").decode(errors="replace")[-1600:] or str(error),
            boundary=joint_pass_id.BOUNDARY,
            metrics={},
            arms={a: {"latlon": None, "forced_latlon": None} for a in ARMS},
        )
    validate_result(result)
    row = dict(
        id=case,
        mode=mode,
        method=joint_pass_id.METHOD,
        result=result,
        offer=offer,
        cpu=cpu,
        worker_wall_s=perf_counter() - start,
        implementation_sha256=sources["joint_pass_id.py"],
        native_sha256=capture.native_sha256,
        catalog_sha256=capture.catalog_sha256,
        input_sha256=hashlib.sha256(data).hexdigest(),
        **binding,
    )
    save_json(scratch / f"{case}-{mode}.json", row)
    print(case, mode, result["status"], round(row["worker_wall_s"], 2), flush=True)
    return row


def replay(scratch, report, cpus):
    if len(cpus) != 4 or len(set(cpus)) != 4 or not set(cpus) <= os.sched_getaffinity(0):
        raise ValueError("choose four distinct available worker CPUs")
    sources = source_digests()
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
                raise ValueError("omitted offer differs from matched archive inputs")
            jobs.append(
                (
                    case,
                    capture,
                    MODES[1],
                    bound["supplied_tile"],
                    {k: bound[k] for k in ("query_id", "query_sha256", "supplied_offer_index")},
                )
            )
    save_json(scratch / "source-lock.json", sources)

    def series(cpu, rows):
        return [trial(*r, cpu, scratch, sources) for r in rows]

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(series, cpu, jobs[i::4]) for i, cpu in enumerate(cpus)]
        results = {(r["id"], r["mode"]): r for batch in futures for r in batch.result()}
    if sources != source_digests():
        raise ValueError("locked implementation changed during archive replay")
    for mode in MODES:
        rows = [results[case, mode] for case in ROSTER if (case, mode) in results]
        write(
            report / f"{mode}.jsonl.gz",
            gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0),
        )
    save_json(report / "source-lock.json", sources)


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
        expected = ROSTER if mode == MODES[0] else ROSTER[3:]
        if tuple(r["id"] for r in rows) != expected or any(r["mode"] != mode for r in rows):
            raise ValueError("prediction roster differs from the declared trial")
        loc, rf = [], []
        for row in rows:
            case, result = row["id"], row["result"]
            for arm in ARMS:
                state = result["arms"][arm]
                ref = refs[case]
                loc.append(
                    dict(
                        id=case,
                        mode=mode,
                        arm=arm,
                        status=result["status"],
                        returned_km=distance_km(state["latlon"], ref["truth"]),
                        forced_km=distance_km(state["forced_latlon"], ref["truth"]),
                        original_v5_km=ref["reference"]["baseline"][arm]["error_km"]
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
                        train_rms_hz=state.get("train_rms_hz"),
                        heldout_rms_hz=state.get("conditional_rms_hz"),
                        heldout_frame_rms_us=state.get("heldout_frame_rms_us"),
                    )
                )
        location.extend(loc)
        frequency.extend(rf)
        summary[mode] = dict(
            count=len(rows),
            arms={
                arm: dict(
                    returned_km=distribution(r["returned_km"] for r in loc if r["arm"] == arm),
                    forced_km=distribution(r["forced_km"] for r in loc if r["arm"] == arm),
                    heldout_rms_hz=distribution(r["heldout_rms_hz"] for r in rf if r["arm"] == arm),
                )
                for arm in ARMS
            },
            paired_fitted_minus_zero={
                key: distribution(
                    records[i + 1][key] - records[i][key]
                    for i in range(0, len(records), 2)
                    if records[i][key] is not None and records[i + 1][key] is not None
                )
                for key, records in (("forced_km", loc), ("heldout_rms_hz", rf))
            },
            worker_wall_s=distribution(r["worker_wall_s"] for r in rows),
        )
    csv_file(report / "position-errors.csv", location)
    csv_file(report / "conditional-frequency.csv", frequency)
    save_json(report / "summary.json", summary)


def audit_fresh_identity(panel, report):
    """Score locked lane identities against the synthetic emitter schedule."""
    lock = json.loads((panel / "prediction-lock.json").read_bytes())
    predictions = (panel / "predictions.jsonl.gz").read_bytes()
    source = json.loads((panel / "source-lock.json").read_bytes())["sources"]
    paths = (
        "tools/pipeline_eval/variants/joint_pass_id.py",
        "tools/pipeline_eval/variants/rate_triplets.py",
    )
    local = source_digests()
    if hashlib.sha256(predictions).hexdigest() != lock["predictions_sha256"] or any(
        source[path] != local[Path(path).name] for path in paths
    ):
        raise ValueError("fresh predictions or source lock differs from the sealed release")
    records = [json.loads(line) for line in gzip.decompress(predictions).splitlines()]
    roster = {(case, method) for case in lock["cases"] for method in lock["methods"]}
    if len(records) != len(roster) or {(r["id"], r["method"]) for r in records} != roster:
        raise ValueError(
            "cannot audit identities before the prospective prediction roster is sealed"
        )
    private = panel / "captures/private"
    labels = json.loads((private / "offer-labels.json").read_bytes())
    truth = json.loads((private / "truth.json").read_bytes())
    rows = []
    for row in records:
        if row["method"] != joint_pass_id.METHOD:
            continue
        label = labels[row["id"]]
        if row["capture_id"] != label["capture_id"]:
            raise ValueError("fresh query and capture label disagree")
        actual = truth[row["capture_id"]]
        schedule = {(a["block"], a["channel"]): a["norad"] for a in actual.get("emitters", [])}
        choices = row["result"]["metrics"].get("associations", [])
        recovered = []
        for arc in choices:
            midpoint = (arc["start_s"] + arc["stop_s"]) / 2
            if schedule.get((int(midpoint // 50), arc["channel"])) == arc["norad"]:
                recovered.append(arc["norad"])
        rows.append(
            {
                "id": row["id"],
                "plant_index": actual["case_index"],
                "condition": label["condition"],
                "correct_lane_identities": len(recovered),
                "selected_lane_identities": len(choices),
                "correct_distinct_emitters": len(set(recovered)),
                "planted_emitters": len(set(schedule.values())),
                "frame_supported_lanes": sum(a["used_frame"] for a in choices),
                **{f"{a}_returned": row["result"]["arms"][a]["latlon"] is not None for a in ARMS},
            }
        )
    csv_file(report / "fresh-identity-audit.csv", rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("replay", "score", "audit-fresh-identity"))
    parser.add_argument("--scratch", type=Path, default=Path("/tmp/leo-joint-pass"))
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--fresh-panel", type=Path)
    parser.add_argument("--cpus", type=int, nargs=4, default=(2, 3, 4, 5))
    args = parser.parse_args()
    scratch, report = local_output(args.scratch), local_output(args.report)
    scratch.mkdir(parents=True, exist_ok=True)
    if args.action == "score":
        score(report)
    elif args.action == "audit-fresh-identity":
        if args.fresh_panel is None:
            parser.error("--fresh-panel is required for the fresh identity audit")
        audit_fresh_identity(args.fresh_panel, report)
    else:
        replay(scratch, report, args.cpus)


if __name__ == "__main__":
    main()
