"""Test anonymous measured Doppler on truth-independent tile-generator draws."""

import argparse
import json
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations, product
from pathlib import Path
from time import perf_counter

import numpy as np

from .. import figure_books
from ..__main__ import ROOT, encoded, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from . import field_anonymous_trial as field
from . import independent_site_omissions as prior
from .armijo_finish_results import pack
from .prefix_figures import csv_file

OUT = ROOT / "reports/2026_11_19_receiver_screening/antenna-confirmation/asymmetric-sites"
ANCHOR = (40.0, -88.0)
SALT = "asymmetric-site-board-stress-20261119-v1"
CORES = (14, 15)
TIMEOUT = 35
PER_CLASS = 3
STREAM = 4096
METHODS = ("asymmetric_held_gain", "asymmetric_old_gate", "asymmetric_interior", "asymmetric_prior")
CONDITIONS = dict(containing="Containing offers", omitted="Omitted by 0.75–3 km")


def generate_boards(key, count=STREAM):
    token = field.digest(encoded((SALT, key)))
    random = np.random.default_rng(int(token, 16))
    lattice = np.asarray(list(product(np.arange(-2, 3) * 42.0, repeat=2)))
    for _ in range(count):
        cells = lattice[random.choice(len(lattice), 4, replace=False)]
        phase = random.uniform(-21.0, 21.0, size=2)
        jitter = random.uniform(-8.0, 8.0, size=(4, 2))
        yield field.receiver.offset(ANCHOR, cells + phase + jitter).tolist()


def classify(tiles, site):
    gaps = [prior.tile_distance(center, site) for center in tiles]
    zero = [i for i, gap in enumerate(gaps) if gap == 0]
    best = min(gaps)
    if len(zero) == 1:
        return "containing", zero[0], 0.0
    if not zero and 0.75 <= best <= 3.0:
        return "omitted", None, best
    return "other", None, best


def select_boards(key, truth):
    stream, selected, counts = [], [], Counter()
    for index, tiles in enumerate(generate_boards(key)):
        stream.append(tiles)
        mode, containing, gap = classify(tiles, truth)
        counts[mode] += 1
        if mode not in CONDITIONS or counts[mode] > PER_CLASS:
            continue
        selected.append((index, tiles, mode, containing, gap))
        if len(selected) == len(CONDITIONS) * PER_CLASS:
            return selected, dict(
                consumed=index + 1,
                sha256=field.digest(encoded(stream)),
                classifications=dict(counts),
            )
    raise ValueError("fixed seed stream has insufficient enrollment")


def geometry(tiles):
    return min(range(4), key=lambda i: distance_km(tiles[i], ANCHOR))


def prepare(raw, work, out):
    work.mkdir(parents=True, mode=0o700)
    jobs, manifest = field.stage(raw, out)
    receipt = json.loads((field.authority.STUDY / "field-receipt.json").read_bytes())
    truth = json.loads(field.authority._verified_truth(receipt))["cases"]
    sites = {r["pair"]: r["latlon"] for r in truth if r["condition"] == "present"}
    records, labels, bases, streams = [], {}, {}, {}
    for job, raw_packet in jobs:
        if job["mode"] != "containing" or job["visit"] != "primary":
            continue
        packet = json.loads(raw_packet)
        del packet["id"], packet["regions"]
        base_sha = field.digest(encoded(packet))
        bases[base_sha] = packet
        site = sites[job["pair"]]
        key = job["source_observation_sha256"]
        selected, streams[key] = select_boards(key, site)
        for index, tiles, condition, contains, gap in selected:
            ident = field.digest(encoded((SALT, base_sha, index)))[:24]
            full = encoded(dict(packet, id=ident, regions=tiles))
            records.append(
                dict(
                    id=ident,
                    base_sha=base_sha,
                    input_sha256=field.digest(full),
                    native_sha256=job["receiver_observation_sha256"],
                    catalogue_sha256=job["catalogue_sha256"],
                    mat_sha256=job["mat_sha256"],
                    tiles=tiles,
                )
            )
            labels[ident] = dict(
                site=job["site"],
                cohort=job["cohort"],
                capture=job["capture"],
                truth=site,
                condition=condition,
                containing_tile=contains,
                nearest_offer_gap_km=gap,
                draw_index=index,
            )
    if len(bases) != 8 or len(records) != 48 or len({r["site"] for r in labels.values()}) != 8:
        raise ValueError("expected eight measured sites with six fixed offers each")
    records.sort(key=lambda row: row["id"])
    names = (
        "requests.json",
        "base-packets.jsonl.gz",
        "geometry-streams.json",
        "source-lock.json",
        "PROTOCOL.md",
    )
    for path in (Path(__file__), Path(prior.__file__)):
        manifest["sources"][str(path.relative_to(ROOT))] = field.digest(path.read_bytes())
    manifest.pop("queries")
    manifest["runtime"]["cpu"] = CORES
    manifest["timeout_s"] = TIMEOUT
    save_json(out / "source-lock.json", manifest)
    save_json(out / "geometry-streams.json", streams)
    save_json(out / "requests.json", records)
    save_json(work / "labels.json", labels)
    pack(
        out, "base-packets.jsonl.gz", [dict(sha256=sha, packet=body) for sha, body in bases.items()]
    )
    prior.seal(
        out,
        "input-lock.json",
        [r["id"] for r in records],
        names,
        label_sha256=field.digest((work / "labels.json").read_bytes()),
    )


def policy(result, tiles):
    stock, interior, _ = prior.alternatives(result)
    gain = result["metrics"].get("null_margin_hz2")
    publish = bool(
        interior["status"] == "ok" and gain is not None and gain > field.receiver.BIN_HZ**2
    )
    if interior["status"] == "ok" and not publish:
        candidate = dict(
            interior,
            status="withheld",
            reason="insufficient_held_time_shift_gain",
            arms={key: dict(value, latlon=None) for key, value in interior["arms"].items()},
        )
    else:
        candidate = interior

    nearest = geometry(tiles)
    only_geometry = dict(
        status="ok",
        reason=None,
        boundary="Prior-nearest offered tile center",
        metrics=dict(best_region=nearest),
        arms=dict(
            c0=dict(latlon=tiles[nearest]),
            fitted_c=dict(
                latlon=None, status="unavailable", reason="geometry_only_has_no_rf_model"
            ),
        ),
    )
    return [prior.identifiable_arms(value) for value in (candidate, stock, interior)] + [
        only_geometry
    ]


def predict(out):
    locked = prior.checked(out, "input-lock.json")
    manifest = json.loads((out / "source-lock.json").read_bytes())
    for name, digest in manifest["sources"].items():
        path = out / "PROTOCOL.md" if name.endswith("/PROTOCOL.md") else ROOT / name
        field.authority._read(path, digest)
    bases = {r["sha256"]: r["packet"] for r in prior.read_rows(out / "base-packets.jsonl.gz")}
    records = json.loads((out / "requests.json").read_bytes())
    if [r["id"] for r in records] != locked["cases"]:
        raise ValueError("frozen query roster differs from receiver requests")

    def lane(cpu, batch):
        rows = []
        for record in batch:
            ident, tiles = record["id"], record["tiles"]
            base = bases[record["base_sha"]]
            raw = encoded(dict(base, id=ident, regions=tiles))
            if field.digest(raw) != record["input_sha256"]:
                raise ValueError("reconstructed receiver packet differs from exact lock")
            cmd = field.authority._sandbox(cpu, [field.SOLVER])
            cmd[-1] = field.WORKER
            start = perf_counter()
            try:
                p = subprocess.run(cmd, input=raw, capture_output=True, check=True, timeout=TIMEOUT)
                answer = json.loads(p.stdout)
                if answer["id"] != ident:
                    raise ValueError("isolated worker returned wrong query")
                result = answer["result"]
            except subprocess.SubprocessError as exc:
                state = "timed_out" if isinstance(exc, subprocess.TimeoutExpired) else "failed"
                result = dict(
                    status=state,
                    reason=(getattr(exc, "stderr", None) or b"").decode()[-900:] or str(exc),
                    boundary=field.receiver.BOUNDARY,
                    metrics={},
                )
            elapsed = perf_counter() - start
            results = policy(result, tiles)
            print(ident, [r["status"] for r in results], f"{elapsed:.2f} s", flush=True)
            for method, decision in zip(METHODS, results, strict=True):
                validate_result(decision)
                rows.append(
                    dict(
                        record,
                        method=method,
                        result=decision,
                        worker_wall_s=0 if method == METHODS[-1] else elapsed,
                    )
                )
        return rows

    with ThreadPoolExecutor(max_workers=len(CORES)) as pool:
        tasks = [pool.submit(lane, cpu, records[i :: len(CORES)]) for i, cpu in enumerate(CORES)]
        rows = [row for task in tasks for row in task.result()]
    pack(out, "positions.jsonl.gz", sorted(rows, key=lambda row: (row["id"], row["method"])))
    prior.seal(
        out, "prediction-lock.json", locked["cases"], ("positions.jsonl.gz", "input-lock.json")
    )


def score(work, out):
    inputs = prior.checked(out, "input-lock.json")
    prediction = prior.checked(out, "prediction-lock.json")
    labels = field.authority._read(work / "labels.json", inputs["label_sha256"])
    truth = json.loads(labels)
    stats, queries, geos = [], {}, {}
    for r in prior.read_rows(out / "positions.jsonl.gz"):
        ident = r["id"]
        label, result, tiles = truth[ident], r["result"], r["tiles"]
        site, condition = label["truth"], label["condition"]
        if classify(tiles, site)[:2] != (condition, label["containing_tile"]):
            raise ValueError("offer geometry disagrees with the locked score label")
        metrics = result["metrics"]
        chosen = metrics.get("best_region")
        queries[ident] = dict(
            id=ident,
            condition=condition,
            truth=site,
            recording=f"{label['capture']}-{label['draw_index']}",
            bindings={k: r[k] for k in ("input_sha256", "native_sha256", "catalogue_sha256")},
        )
        if r["method"] == METHODS[-1]:
            midpoints = [np.mean(points, axis=0).tolist() for points in combinations(tiles, 2)]
            geos[ident] = dict(
                id=ident,
                **label,
                prior_center_error_km=distance_km(ANCHOR, site),
                nearest_center_error_km=distance_km(tiles[geometry(tiles)], site),
                first_center_error_km=distance_km(tiles[0], site),
                first_center_tile_hit=label["containing_tile"] == 0,
                prior_nearest_tile_hit=label["containing_tile"] == chosen,
                midpoint_error_km=distance_km(np.mean(tiles, axis=0).tolist(), site),
                best_pair_midpoint_error_km=min(distance_km(p, site) for p in midpoints),
            )
        for name in ARMS:
            arm = result.get("arms", {}).get(name, {})
            published = arm.get("latlon")
            stats.append(
                dict(
                    id=ident,
                    group=label["site"],
                    cohort=label["cohort"],
                    method=r["method"],
                    arm=name,
                    condition=condition,
                    status=arm.get("status", result["status"]),
                    reason=arm.get("reason", result["reason"]),
                    published=published is not None,
                    false_fix=condition == "omitted" and published is not None,
                    published_error_km=distance_km(published, site),
                    forced_error_km=distance_km(arm.get("forced_latlon"), site),
                    held_rms_hz=arm.get("rf_rms_hz"),
                    time_null_rms_hz=metrics.get("time_control_capped_rms_hz")
                    if name == "c0"
                    else None,
                    held_lead_hz2=metrics.get("null_margin_hz2") if name == "c0" else None,
                    edge_km=metrics.get("edge_km"),
                    correct_tile=condition == "containing" and chosen == label["containing_tile"],
                    offer_gap_km=label["nearest_offer_gap_km"],
                    worker_wall_s=r["worker_wall_s"],
                    worker_cpu_s=metrics.get("solve_cpu_s"),
                )
            )
    if len(stats) != 48 * len(METHODS) * len(ARMS) or set(geos) != set(prediction["cases"]):
        raise ValueError("scored requests do not cover the enrolled panel")
    csv_file(out / "scores.csv", stats)
    csv_file(out / "geometry.csv", list(geos.values()))
    write(out / "truth-after-lock.json", labels)
    save_json(out / "figure-queries.json", dict(queries=[queries[i] for i in prediction["cases"]]))
    save_json(
        out / "score-source.json", dict(scorer_sha256=field.digest(Path(__file__).read_bytes()))
    )
    prior.seal(
        out,
        "score-lock.json",
        prediction["cases"],
        (
            "positions.jsonl.gz",
            "prediction-lock.json",
            "scores.csv",
            "geometry.csv",
            "score-source.json",
            "truth-after-lock.json",
            "figure-queries.json",
        ),
    )


def chart(out):
    ident = "asymmetric-measured-site-offers"
    keys = ("candidate", "stock", "one", "four")
    labels = ("Held time gain", "Old held gate", "Interior only", "Prior-only center")
    series = [
        dict(
            key=k, label=label, forced_label=f"{label} · forced", value=m, file="positions.jsonl.gz"
        )
        for k, label, m in zip(keys, labels, METHODS, strict=True)
    ]
    for row in series[1:]:
        row["match"] = ["input_sha256", "native_sha256", "catalogue_sha256"]
    save_json(
        out / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id=ident,
                    method=METHODS[0],
                    scope="transfer",
                    title="Asymmetric offers at eight measured sites",
                    cases="sealed",
                    seal="score-lock.json",
                    queries="figure-queries.json",
                    series=series,
                    provenance=["prediction-lock.json", "scores.csv", "geometry.csv"],
                    condition_labels=CONDITIONS,
                    caption="48 boards on one measured beacon instrument. The seeded lattice and "
                    "prior-only center share a coarse Illinois anchor. Fitted c is unidentifiable.",
                )
            ],
        ),
    )
    figure_books.generate(out / "charts", ARMS, methods=[ident], panel="screening", evidence=out)


def main():
    arg = argparse.ArgumentParser(description=__doc__)
    arg.add_argument("action", choices=("prepare", "predict", "score", "chart"))
    arg.add_argument("work", type=Path)
    arg.add_argument("--out", type=Path, default=OUT)
    arg.add_argument("--raw", type=Path)
    cfg = arg.parse_args()
    if cfg.action == "prepare":
        prepare(cfg.raw, cfg.work, cfg.out)
    elif cfg.action == "score":
        score(cfg.work, cfg.out)
    else:
        {"predict": predict, "chart": chart}[cfg.action](cfg.out)


if __name__ == "__main__":
    main()
