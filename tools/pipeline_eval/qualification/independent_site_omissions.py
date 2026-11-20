"""Challenge the frozen anonymous field receiver on new mixed tile boards."""

import argparse
import gzip
import json
import subprocess
from collections import Counter
from pathlib import Path
from time import perf_counter

import numpy as np

from .. import figure_books
from ..__main__ import ROOT, encoded, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from . import field_anonymous_trial as field
from .armijo_finish_results import pack
from .prefix_figures import csv_file

OUT = ROOT / "reports/2026_11_19_receiver_screening/pilot-influence/independent-site"
CPU = 6
TIMEOUT_S = 35
SALT = "independent-field-tile-geometry-v1-20261119"
CONDITIONS = {
    "containing": "Contains receiver",
    "face": "1 km beyond face",
    "corner": "1 km past both corner axes",
    "far": "20 km beyond face",
}
METHODS = ("starloc_new_boards_held", "starloc_new_boards_interior", "starloc_new_boards_ungated")
ARTIFACT = "positions.jsonl.gz"
PUBLIC = "requests.jsonl.gz"
LABEL = "labels.json"


def local_coordinates(center, point):
    lat0, lon0 = np.deg2rad(center)
    lat1, lon1 = np.deg2rad(point)
    east = np.cos(lat1) * np.sin(lon1 - lon0)
    north = np.cos(lat0) * np.sin(lat1) - np.sin(lat0) * np.cos(lat1) * np.cos(lon1 - lon0)
    cosine = np.sin(lat0) * np.sin(lat1) + np.cos(lat0) * np.cos(lat1) * np.cos(lon1 - lon0)
    angle = np.arctan2(np.hypot(east, north), cosine)
    direction = np.arctan2(east, north)
    return 6371.0 * angle * np.array([np.sin(direction), np.cos(direction)])


def make_boards(site, key):
    token = bytes.fromhex(field.digest(encoded([SALT, key])))
    offset = {"containing": (5, 3), "face": (13.5, 4), "corner": (13.5, 13.5), "far": (32.5, 4)}

    def orient(values):
        east, north = values
        if token[0] % 2:
            east, north = north, east
        return (east * (-1 if token[1] % 2 else 1), north * (-1 if token[2] % 2 else 1))

    decoys = [(0, 75), (0, -75), (-75, 0)]
    boards = {}
    for condition, shift in offset.items():
        ordered = [shift, *decoys]
        indices = sorted(range(4), key=lambda i: token[3 + i])
        centers = field.receiver.offset(site, np.asarray([orient(ordered[i]) for i in indices]))
        contained = [i for i, center in enumerate(centers) if tile_distance(center, site) == 0]
        if contained != ([indices.index(0)] if condition == "containing" else []):
            raise ValueError("new board polarity does not hold in the receiver's tile geometry")
        boards[condition] = centers.tolist()
    return boards


def tile_distance(center, point):
    excess = np.maximum(0, abs(local_coordinates(center, point)) - field.receiver.TILE_KM)
    return float(np.linalg.norm(excess))


def seal(out, name, ids, filenames, **extra):
    save_json(
        out / name,
        dict(
            cases=ids, files={n: field.digest((out / n).read_bytes()) for n in filenames}, **extra
        ),
    )


def checked(out, name):
    data = json.loads((out / name).read_bytes())
    for n, h in data["files"].items():
        field.authority._read(out / n, h)
    return data


def read_rows(path):
    with gzip.open(path, "rt") as handle:
        return [json.loads(line) for line in handle]


def prepare(raw, work, out):
    work.mkdir(parents=True, mode=0o700)
    jobs, manifest = field.stage(raw, out)
    receipt = json.loads((field.authority.STUDY / "field-receipt.json").read_bytes())
    private = json.loads(field.authority._verified_truth(receipt))
    source = {r["pair"]: r for r in private["cases"] if r["condition"] == "present"}
    archived = {}
    for job, _ in jobs:
        if job["mode"] == "worldwide":
            continue
        archived.setdefault(job["pair"], []).extend(region["center"] for region in job["regions"])
    records, labels = [], {}
    for job, packet in jobs:
        if job["visit"] != "primary" or job["mode"] != "containing":
            continue
        location = source[job["pair"]]["latlon"]
        for condition, tiles in make_boards(location, job["site"]).items():
            if any(
                distance_km(center, old) <= 0.1 for center in tiles for old in archived[job["pair"]]
            ):
                raise ValueError("new tile is too close to an existing offered center")
            ident = field.digest(encoded([SALT, job["input_sha256"], condition]))[:24]
            raw_packet = encoded(dict(json.loads(packet), id=ident, regions=tiles))
            records.append(
                dict(
                    id=ident,
                    input_sha256=field.digest(raw_packet),
                    native_sha256=job["receiver_observation_sha256"],
                    catalogue_sha256=job["catalogue_sha256"],
                    mat_sha256=job["mat_sha256"],
                    body=raw_packet.decode(),
                )
            )
            labels[ident] = dict(
                site=job["site"],
                capture=job["capture"],
                truth=location,
                condition=condition,
                min_offer_gap_km=min(tile_distance(c, location) for c in tiles),
                center_error_km=min(distance_km(c, location) for c in tiles),
            )
    if len(records) != 32 or len({r["site"] for r in labels.values()}) != 8:
        raise ValueError("full prospective eight-site board study expected")
    records.sort(key=lambda r: r["id"])
    manifest["sources"][str(Path(__file__).relative_to(ROOT))] = field.digest(
        Path(__file__).read_bytes()
    )
    manifest.pop("queries")
    manifest["runtime"]["cpu"] = CPU
    manifest["timeout_s"] = TIMEOUT_S
    save_json(out / "source-lock.json", manifest)
    pack(out, PUBLIC, records)
    save_json(work / LABEL, labels)
    seal(
        out,
        "input-lock.json",
        [r["id"] for r in records],
        (PUBLIC, "source-lock.json", "PROTOCOL.md"),
        label_sha256=field.digest((work / LABEL).read_bytes()),
    )


def alternatives(result):
    if result["status"] not in ("ok", "withheld"):
        return (result,) * 3
    arms = result["arms"]
    point = arms["c0"]["forced_latlon"]
    slack = result["metrics"].get("edge_km")
    interior = point is not None and slack is not None and slack >= field.receiver.END_MARGIN_KM

    def decision(allowed, reason):
        return dict(
            result,
            status="ok" if allowed else "withheld",
            reason=None if allowed else reason,
            arms={key: dict(arm, latlon=point if allowed else None) for key, arm in arms.items()},
        )

    return (
        result,
        decision(interior, "interior_only_rejected"),
        decision(point is not None, "no_eligible_geometry"),
    )


def identifiable_arms(result):
    if "arms" not in result:
        return result
    arms = result["arms"]
    if arms["c0"] != arms["fitted_c"]:
        raise ValueError("one-RF receiver unexpectedly returned independently fitted calibration")
    fitted = dict(
        status="unavailable", reason="single_rf_projected_by_per_arc_intercepts", latlon=None
    )
    return dict(result, arms=dict(c0=arms["c0"], fitted_c=fitted))


def predict(out):
    input_lock = checked(out, "input-lock.json")
    manifest = json.loads((out / "source-lock.json").read_bytes())
    for name, digest in manifest["sources"].items():
        path = out / "PROTOCOL.md" if name.endswith("/PROTOCOL.md") else ROOT / name
        field.authority._read(path, digest)
    rows, batches = [], []
    for request in read_rows(out / PUBLIC):
        plain = request.pop("body").encode()
        ident = request["id"]
        if field.digest(plain) != request["input_sha256"]:
            raise ValueError("request body changed")
        cmd = field.authority._sandbox(CPU, [field.SOLVER])
        cmd[-1] = field.WORKER
        start = perf_counter()
        try:
            run = subprocess.run(
                cmd, input=plain, capture_output=True, check=True, timeout=TIMEOUT_S
            )
            answer = json.loads(run.stdout)
            if answer["id"] != ident:
                raise ValueError("isolation returned a mismatched request")
            result = answer["result"]
        except subprocess.SubprocessError as failure:
            status = "timed_out" if isinstance(failure, subprocess.TimeoutExpired) else "failed"
            result = dict(
                status=status, reason=str(failure), boundary=field.receiver.BOUNDARY, metrics={}
            )
        elapsed = perf_counter() - start
        results = alternatives(result)
        for method, response in zip(METHODS, results, strict=True):
            response = identifiable_arms(response)
            validate_result(response)
            rows.append(dict(request, method=method, result=response, worker_wall_s=elapsed))
        batches.append(ident)
        print(ident, [r["status"] for r in results], f"{elapsed:.2f} s", flush=True)
    if batches != input_lock["cases"]:
        raise ValueError("worker roster differs from frozen geometry input")
    pack(out, ARTIFACT, rows)
    seal(out, "prediction-lock.json", batches, (ARTIFACT, "input-lock.json"))


def score(work, out):
    input_lock = checked(out, "input-lock.json")
    prediction = checked(out, "prediction-lock.json")
    private = field.authority._read(work / LABEL, input_lock["label_sha256"])
    truth = json.loads(private)
    stats, queries = [], {}
    counts = Counter()
    for row in read_rows(out / ARTIFACT):
        ident, method, result = row["id"], row["method"], row["result"]
        label = truth[ident]
        query = dict(
            id=ident,
            condition=label["condition"],
            truth=label["truth"],
            recording=label["capture"],
            bindings={k: row[k] for k in ("input_sha256", "native_sha256", "catalogue_sha256")},
        )
        queries[ident] = query
        for arm_name in ARMS:
            arm = result.get("arms", {}).get(arm_name, {})
            fitted, forced = arm.get("latlon"), arm.get("forced_latlon")
            status = arm.get("status", result["status"])
            counts[method, label["condition"], arm_name, status] += 1
            stats.append(
                dict(
                    id=ident,
                    site=label["site"],
                    arm=arm_name,
                    method=method,
                    condition=label["condition"],
                    status=status,
                    reason=arm.get("reason", result["reason"]),
                    published=fitted is not None,
                    false_fix=label["condition"] != "containing" and fitted is not None,
                    error_km=distance_km(fitted, label["truth"]),
                    forced_error_km=distance_km(forced, label["truth"]),
                    held_rms_hz=arm.get("rf_rms_hz"),
                    edge_km=result["metrics"].get("edge_km"),
                    spatial_margin_hz2=result["metrics"].get("spatial_margin_hz2"),
                    support_orbits=len(set(result["metrics"].get("held_ids", []))),
                    min_offer_gap_km=label["min_offer_gap_km"],
                    center_error_km=label["center_error_km"],
                    worker_wall_s=row["worker_wall_s"],
                    solve_cpu_s=result["metrics"].get("solve_cpu_s"),
                )
            )
    if len(stats) != 32 * len(METHODS) * len(ARMS):
        raise ValueError("expected all decisions on every site and board")
    csv_file(out / "scores.csv", stats)
    write(out / "truth-after-lock.json", private)
    save_json(
        out / "counts.json",
        [
            {"method": m, "condition": c, "arm": a, "status": s, "count": n}
            for (m, c, a, s), n in sorted(counts.items())
        ],
    )
    save_json(out / "figure-queries.json", dict(queries=[queries[i] for i in prediction["cases"]]))
    seal(
        out,
        "score-lock.json",
        prediction["cases"],
        (
            ARTIFACT,
            "prediction-lock.json",
            "scores.csv",
            "truth-after-lock.json",
            "counts.json",
            "figure-queries.json",
        ),
    )


def chart(out):
    ident = "independent-site-omission-frontier"
    x = [
        dict(key=key, label=label, forced_label=forced, file=ARTIFACT, value=method)
        for key, label, forced, method in zip(
            ("candidate", "stock", "one"),
            ("Held gate", "Interior only", "Ungated"),
            ("Held gate · forced", "Interior only · forced", "Ungated · forced"),
            METHODS,
            strict=True,
        )
    ]
    for series in x[1:]:
        series["match"] = ["input_sha256", "native_sha256", "catalogue_sha256"]
    save_json(
        out / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id=ident,
                    method=METHODS[0],
                    title="Geographic false publication on eight measured beacon sites",
                    scope="transfer",
                    cases="sealed",
                    seal="score-lock.json",
                    queries="figure-queries.json",
                    series=x,
                    provenance=["prediction-lock.json", "scores.csv"],
                    condition_labels=CONDITIONS,
                    caption="Four new boards per site, one receiver installation, one nominal RF. "
                    "Matched searches share anonymous measured tracks. Fitted c is unidentifiable.",
                )
            ],
        ),
    )
    figure_books.generate(out / "charts", ARMS, methods=[ident], panel="screening", evidence=out)


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("action", choices=("prepare", "predict", "score", "chart"))
    args.add_argument("work", type=Path)
    args.add_argument("--raw", type=Path)
    args.add_argument("--out", type=Path, default=OUT)
    cfg = args.parse_args()
    if cfg.action == "prepare":
        prepare(cfg.raw, cfg.work, cfg.out)
    elif cfg.action == "score":
        score(cfg.work, cfg.out)
    else:
        {"predict": predict, "chart": chart}[cfg.action](cfg.out)


if __name__ == "__main__":
    main()
