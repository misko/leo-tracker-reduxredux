"""Freeze, execute and score the regional outside option on the same field traces."""

import argparse
import json
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from .. import figure_books
from ..__main__ import ROOT, encoded, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from ..variants import outside_option_field as solver
from . import asymmetric_site_trial as geometry
from . import field_anonymous_trial as field
from . import independent_site_omissions as prior
from .armijo_finish_results import pack
from .prefix_figures import csv_file

OUT = ROOT / "reports/2026_11_19_receiver_screening/original-support/outside-option"
SEED = "field-outside-option-20261119-v1"
SOLVER = Path(solver.__file__)
CPU = (14, 15)
CAP_S = 40
CONDITIONS = dict(
    containing="Containing", near="Near omission · 0.75–3 km", wide="Wide omission · 12.5–22 km"
)
METHODS = (
    "outside_option_field",
    "outside_stock",
    "outside_interior",
    "outside_prior",
    "outside_unconstrained",
    "outside_only",
)
WORKER = """
import hashlib
import json
import sys
from pathlib import Path
import outside_option
import solver

r = json.load(sys.stdin)
assert hashlib.sha256(Path(solver.__file__).read_bytes()).hexdigest() == r['solver_sha256']
assert hashlib.sha256(Path(outside_option.__file__).read_bytes()).hexdigest() == r['outside_sha256']
value = outside_option.solve(r['observation'], r['catalogue'], r['regions'])
json.dump(dict(id=r['id'], **value), sys.stdout, allow_nan=False)
"""


def enroll(key, truth):
    stream, counts, selected = [], Counter(), []
    for i, tiles in enumerate(geometry.generate_boards((SEED, key))):
        stream.append(tiles)
        mode, hit, gap = geometry.classify(tiles, truth)
        mode = {"containing": "containing", "omitted": "near"}.get(mode, "other")
        if 12.5 <= gap <= 22.0:
            mode = "wide"
        counts[mode] += 1
        if mode in CONDITIONS and counts[mode] <= 2:
            selected.append((i, tiles, mode, hit, gap))
        if len(selected) == 2 * len(CONDITIONS):
            return selected, dict(
                consumed=i + 1, counts=dict(counts), sha256=field.digest(encoded(stream))
            )
    raise ValueError("external-conformance offer roster exhausted the fixed seed")


def prepare(raw_root, work, out):
    work.mkdir(parents=True, mode=0o700)
    jobs, lock = field.stage(raw_root, out)
    receipt = json.loads((field.authority.STUDY / "field-receipt.json").read_bytes())
    truth = json.loads(field.authority._verified_truth(receipt))["cases"]
    survey = {r["pair"]: r["latlon"] for r in truth if r["condition"] == "present"}
    records, labels, packets, streams = [], {}, {}, {}
    for job, raw in jobs:
        if (job["mode"], job["visit"]) != ("containing", "primary"):
            continue
        base = json.loads(raw)
        del base["id"], base["regions"]
        base["outside_sha256"] = field.digest(SOLVER.read_bytes())
        base_sha = field.digest(encoded(base))
        packets[base_sha] = base
        site, key = survey[job["pair"]], job["source_observation_sha256"]
        chosen, streams[key] = enroll(key, site)
        for i, tiles, mode, hit, gap in chosen:
            ident = field.digest(encoded((SEED, base_sha, i)))[:24]
            packet = encoded(dict(base, id=ident, regions=tiles))
            records.append(
                dict(
                    id=ident,
                    base_sha=base_sha,
                    tiles=tiles,
                    input_sha256=field.digest(packet),
                    native_sha256=job["receiver_observation_sha256"],
                    catalogue_sha256=job["catalogue_sha256"],
                    mat_sha256=job["mat_sha256"],
                )
            )
            labels[ident] = dict(
                site=job["site"],
                cohort=job["cohort"],
                capture=job["capture"],
                condition=mode,
                containing_tile=hit,
                truth=site,
                index=i,
                gap_km=gap,
            )
    if len(records) != 48 or len(packets) != 8:
        raise ValueError("expected matched 48-board/eight-site qualification")
    records.sort(key=lambda row: row["id"])
    del lock["queries"]
    for path in (SOLVER, Path(__file__), Path(geometry.__file__), Path(prior.__file__)):
        lock["sources"][str(path.relative_to(ROOT))] = field.digest(path.read_bytes())
    lock["runtime"]["cpu"] = CPU
    lock["timeout_s"] = CAP_S
    save_json(out / "source-lock.json", lock)
    save_json(out / "requests.json", records)
    save_json(out / "draw-streams.json", streams)
    save_json(work / "labels.json", labels)
    pack(out, "base-packets.jsonl.gz", [dict(sha=h, base=p) for h, p in packets.items()])
    names = (
        "PROTOCOL.md",
        "source-lock.json",
        "requests.json",
        "draw-streams.json",
        "base-packets.jsonl.gz",
    )
    prior.seal(
        out,
        "input-lock.json",
        [r["id"] for r in records],
        names,
        label_sha256=field.digest((work / "labels.json").read_bytes()),
    )


def prior_only(tiles):
    i = geometry.geometry(tiles)
    return dict(
        status="ok",
        reason=None,
        boundary="Coarse-prior nearest offered tile center",
        metrics=dict(best_region=i),
        arms=dict(
            c0=dict(latlon=tiles[i]),
            fitted_c=dict(latlon=None, status="unavailable", reason="prior_only_has_no_rf_model"),
        ),
    )


def policy_rows(payload, tiles):
    candidate, ordinary = (payload[k] for k in ("candidate", "ordinary"))
    stock, interior, _ = prior.alternatives(ordinary)
    metrics = candidate["metrics"]

    def forced(point, rms, reason):
        arm = dict(latlon=None, forced_latlon=metrics.get(point), rf_rms_hz=metrics.get(rms))
        return dict(
            status="withheld",
            reason=reason,
            boundary=solver.BOUNDARY,
            metrics=metrics,
            arms=dict(c0=arm, fitted_c=dict(arm)),
        )

    numerical = [
        candidate,
        stock,
        interior,
        forced("unconstrained_latlon", "unconstrained_held_rms_hz", "forced_branch_audit"),
        forced("outside_candidate_latlon", "outside_held_rms_hz", "forced_exterior_audit"),
    ]
    published = [prior.identifiable_arms(value) for value in numerical]
    return [*published[:3], prior_only(tiles), *published[3:]]


def predict(out):
    locked = prior.checked(out, "input-lock.json")
    manifest = json.loads((out / "source-lock.json").read_bytes())
    for name, digest in manifest["sources"].items():
        path = out / "PROTOCOL.md" if name.endswith("/PROTOCOL.md") else ROOT / name
        field.authority._read(path, digest)
    bases = {r["sha"]: r["base"] for r in prior.read_rows(out / "base-packets.jsonl.gz")}
    records = json.loads((out / "requests.json").read_bytes())
    if [r["id"] for r in records] != locked["cases"]:
        raise ValueError("receiver requests do not match the enrolled roster")

    def batch(core, requests):
        rows = []
        for r in requests:
            ident, tiles = r["id"], r["tiles"]
            raw = encoded(dict(bases[r["base_sha"]], id=ident, regions=tiles))
            if field.digest(raw) != r["input_sha256"]:
                raise ValueError("opaque receiver request changed")
            base = field.authority._sandbox(core, [field.SOLVER])
            cmd = [
                *base[:-4],
                "--ro-bind",
                str(SOLVER),
                "/worker/outside_option.py",
                *base[-4:-1],
                WORKER,
            ]
            start = perf_counter()
            try:
                run = subprocess.run(cmd, input=raw, capture_output=True, check=True, timeout=CAP_S)
                answer = json.loads(run.stdout)
                if answer["id"] != ident:
                    raise ValueError("isolated worker returned the wrong request")
                results = policy_rows(answer, tiles)
            except subprocess.SubprocessError as exc:
                state = "timed_out" if isinstance(exc, subprocess.TimeoutExpired) else "failed"
                detail = (getattr(exc, "stderr", None) or b"").decode(errors="replace")[-900:]
                failure = dict(
                    status=state, reason=detail or str(exc), boundary=solver.BOUNDARY, metrics={}
                )
                results = [failure, failure, failure, prior_only(tiles), failure, failure]
            elapsed = perf_counter() - start
            print(ident, [r["status"] for r in results[:3]], f"{elapsed:.2f} s", flush=True)
            for method, result in zip(METHODS, results, strict=True):
                validate_result(result)
                rows.append(
                    dict(
                        r,
                        method=method,
                        result=result,
                        worker_wall_s=None if method == METHODS[3] else elapsed,
                    )
                )
        return rows

    with ThreadPoolExecutor(max_workers=len(CPU)) as pool:
        tasks = [pool.submit(batch, core, records[i :: len(CPU)]) for i, core in enumerate(CPU)]
        rows = [row for task in tasks for row in task.result()]
    pack(out, "positions.jsonl.gz", sorted(rows, key=lambda row: (row["id"], row["method"])))
    prior.seal(
        out, "prediction-lock.json", locked["cases"], ("positions.jsonl.gz", "input-lock.json")
    )


def score(work, out):
    lock = prior.checked(out, "input-lock.json")
    pred = prior.checked(out, "prediction-lock.json")
    labels = field.authority._read(work / "labels.json", lock["label_sha256"])
    truth = json.loads(labels)
    queries, values, challenges = {}, [], []
    for r in prior.read_rows(out / "positions.jsonl.gz"):
        ident, method, result = (r[k] for k in ("id", "method", "result"))
        label = truth[ident]
        site, condition = label["truth"], label["condition"]
        metrics = result["metrics"]
        queries[ident] = dict(
            id=ident,
            condition=condition,
            truth=site,
            recording=f"{label['capture']}-{label['index']}",
            bindings={k: r[k] for k in ("input_sha256", "native_sha256", "catalogue_sha256")},
        )
        for name in ARMS:
            arm = result.get("arms", {}).get(name, {})
            fix = arm.get("latlon")
            values.append(
                dict(
                    id=ident,
                    method=method,
                    arm=name,
                    group=label["site"],
                    cohort=label["cohort"],
                    condition=condition,
                    status=arm.get("status", result["status"]),
                    reason=arm.get("reason", result["reason"]),
                    published=fix is not None,
                    false_fix=condition != "containing" and fix is not None,
                    error_km=distance_km(fix, site),
                    forced_error_km=distance_km(arm.get("forced_latlon"), site),
                    rf_rms_hz=arm.get("rf_rms_hz"),
                    worker_wall_s=r["worker_wall_s"],
                )
            )
        if method == METHODS[0]:
            challenges.append(
                dict(
                    id=ident,
                    group=label["site"],
                    cohort=label["cohort"],
                    condition=condition,
                    truth_offer_gap_km=label["gap_km"],
                    inside_error_km=distance_km(metrics.get("inside_candidate_latlon"), site),
                    outside_error_km=distance_km(metrics.get("outside_candidate_latlon"), site),
                    unconstrained_error_km=distance_km(metrics.get("unconstrained_latlon"), site),
                    **{
                        k: metrics.get(k)
                        for k in (
                            "inside_training_rms_hz",
                            "outside_training_rms_hz",
                            "inside_held_rms_hz",
                            "outside_held_rms_hz",
                            "outside_gap_km",
                            "inside_face_km",
                            "early_inside_gain_hz2",
                            "held_inside_gain_hz2",
                            "unconstrained_branch",
                            "outside_coarse_points",
                            "inside_eligible_points",
                            "outside_eligible_points",
                            "outside_tried_points",
                            "preparation_wall_s",
                            "baseline_wall_s",
                            "baseline_cpu_s",
                            "joint_wall_s",
                            "joint_cpu_s",
                        )
                    },
                )
            )
    if len(values) != 48 * len(METHODS) * len(ARMS) or len(challenges) != 48:
        raise ValueError("incomplete outside-option score roster")
    csv_file(out / "scores.csv", values)
    csv_file(out / "hypotheses.csv", challenges)
    save_json(out / "figure-queries.json", dict(queries=[queries[i] for i in pred["cases"]]))
    write(out / "truth-after-lock.json", labels)
    names = (
        "positions.jsonl.gz",
        "prediction-lock.json",
        "scores.csv",
        "hypotheses.csv",
        "figure-queries.json",
        "truth-after-lock.json",
    )
    prior.seal(out, "score-lock.json", pred["cases"], names)


def chart(out):
    def series(k, label, i):
        r = dict(
            key=k,
            label=label,
            forced_label=f"{label} · forced",
            value=METHODS[i],
            file="positions.jsonl.gz",
        )
        if k != "candidate":
            r["match"] = ["input_sha256", "native_sha256", "catalogue_sha256"]
        return r

    common = dict(
        scope="transfer",
        cases="sealed",
        seal="score-lock.json",
        queries="figure-queries.json",
        provenance=["prediction-lock.json", "scores.csv", "hypotheses.csv"],
        condition_labels=CONDITIONS,
    )
    chart_specs = [
        dict(
            common,
            id="field-outside-option-publication",
            method=METHODS[0],
            title="Publishing measured beacon positions against an explicit outside option",
            caption="Eight existing sites, 48 new boards. Both hypotheses use the same "
            "anonymous traces and drift model. Fitted c is unidentifiable at one RF.",
            series=[
                series("candidate", "Outside gate", 0),
                series("stock", "Old full gate", 1),
                series("one", "Interior only", 2),
                series("four", "Prior-only center", 3),
            ],
        ),
        dict(
            common,
            id="field-outside-option-forced",
            method=METHODS[4],
            title="Forced positions from inside and exterior beacon hypotheses",
            caption="Forced coordinates compare the training winner across both regions, "
            "the exterior-only fit and the offered inside fit. Fitted c is unavailable.",
            series=[
                series("candidate", "Unrestricted", 4),
                series("stock", "Exterior", 5),
                series("one", "Offered inside", 0),
                series("four", "Prior-only center", 3),
            ],
        ),
    ]
    save_json(out / "figures.json", dict(version=2, charts=chart_specs))
    figure_books.generate(
        out / "charts",
        ARMS,
        methods=[r["id"] for r in chart_specs],
        panel="screening",
        evidence=out,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "predict", "score", "chart"))
    parser.add_argument("work", type=Path)
    parser.add_argument("--raw", type=Path)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.raw, args.work, args.out)
    elif args.action == "score":
        score(args.work, args.out)
    else:
        {"predict": predict, "chart": chart}[args.action](args.out)


if __name__ == "__main__":
    main()
