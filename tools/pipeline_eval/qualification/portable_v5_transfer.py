"""Draw and score two fresh synthetic native scenes with genuine prior TLE snapshots."""

import argparse
import gzip
import hashlib
import json
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants import orbit_projector
from ..variants.rate_triplets import offset_site
from . import cold_scenes as scene
from .portable_v5_trials import (
    REPORT,
    checksum,
    portable_trial,
    preferred_history,
    source_lock,
)
from .prefix_figures import csv_file

SITE_BOXES = ((51.0, 11.0), (-23.0, 30.0))
MODES = ("matched-tile", "omitted-tile")
CASE_S = 180


def authentic_history():
    pinned = json.loads(scene.SNAPSHOT.read_bytes())
    received_dt = datetime.fromisoformat(pinned["retrieved_at"])
    received = scene._stamp(received_dt)
    nominal_path = scene.TLE_ARCHIVE / pinned["raw_object"]
    nominal = nominal_path.read_bytes()
    if hashlib.sha256(nominal).hexdigest() != scene.CATALOG_SHA256:
        raise ValueError("the frozen generator catalogue changed")
    if scene._stamp(datetime.fromisoformat(pinned["tle_epoch_max"])) > received:
        raise ValueError("generator nominal catalogue contains a post-collection element")
    oldest = received_dt - timedelta(hours=72)
    entries = {}
    verified = {}
    for day in range(4):
        date = received_dt - timedelta(days=day)
        leaf = scene.SNAPSHOT.parents[3] / date.strftime("%Y/%m/%d")
        for manifest in sorted(leaf.glob("*.json")):
            data = json.loads(manifest.read_bytes())
            when = datetime.fromisoformat(data["retrieved_at"])
            if not oldest <= when <= received_dt:
                continue
            raw = scene.TLE_ARCHIVE / data["raw_object"]
            digest = data["raw_sha256"]
            if digest not in verified:
                if checksum(raw) != digest:
                    raise ValueError("history raw TLE differs from its archived digest")
                verified[digest] = raw
            elif verified[digest] != raw:
                raise ValueError("one history digest maps to different raw object paths")
            entries[scene._stamp(when), digest] = dict(
                collected_utc_ns=scene._stamp(when),
                sha256=digest,
                source_manifest_sha256=checksum(manifest),
                source_manifest=manifest.name,
            )
    return received, nominal, list(entries.values()), verified


def simulated_document(ident, anchor, probes, counter):
    """Create simulator-owned clock authority from the public sample-counter schedule."""
    monotonic = 10_000_000_000
    delay = 5_000_000

    def clock(relative):
        return dict(realtime_ns=anchor + relative, monotonic_ns=monotonic + relative)

    end = counter + scene.SECONDS * scene.RATE
    last = max(p["valid_start_counter"] for p in probes)
    if last + scene.PROBE_MS * scene.RATE // 1000 > end:
        raise ValueError("synthetic probe crosses the public capture bound")
    clocks = [
        clock((p - counter) * scene.NS // scene.RATE + scene.PROBE_MS * 1_000_000)
        for p in sorted({r["valid_start_counter"] for r in probes})
    ]
    return dict(
        schema_version=1,
        clock_anchor=dict(sample_counter=counter, before=clock(-delay), after=clock(delay)),
        delivery_clocks=clocks,
        last_sample_counter=end,
        source=dict(
            session_id=ident,
            probe_ms=scene.PROBE_MS,
            sample_rate_hz=scene.RATE,
            qualified=True,
            probes=probes,
        ),
        provenance=dict(
            run_id=ident,
            window_count=len(clocks),
            processed_windows=len(clocks),
            excluded_windows=[],
            invalid_capture=0,
            skipped_fast_score=0,
            rf_mapping_authorities=["simulation"],
            scope="synthetic native measurement authority",
        ),
    )


def offered_tile(site, bearing, km, ident):
    east, north = km * np.sin(bearing), km * np.cos(bearing)
    return dict(id=ident, center=offset_site(site, east, north).tolist(), width_km=25.0)


def new_scenes(seed):
    received, nominal, archival, objects = authentic_history()
    elements = scene._constellation(nominal, received)
    rng = np.random.default_rng(int.from_bytes(seed, "big"))
    jobs, answers = [], {}
    for index, center in enumerate(SITE_BOXES):
        site = tuple(map(float, np.asarray(center) + rng.uniform(-4, 4, size=2)))
        ident = rng.bytes(12).hex()
        anchor = received + (480 + index * 360) * scene.NS
        probes, counter, _ = scene._generate_capture(elements, anchor, site, rng)
        doc = simulated_document(ident, anchor, probes, counter)
        cutoff = doc["clock_anchor"]["before"]["realtime_ns"]
        stamps = preferred_history(
            [{k: r[k] for k in ("sha256", "collected_utc_ns")} for r in archival],
            cutoff,
        )
        allowed = {r["sha256"]: objects[r["sha256"]] for r in stamps}
        tiles = (
            offered_tile(site, rng.uniform(0, 2 * np.pi), rng.uniform(8, 10), "present"),
            offered_tile(site, rng.uniform(0, 2 * np.pi), rng.uniform(70, 100), "omitted"),
        )
        jobs.extend(
            (ident, mode, doc, tile, stamps, allowed)
            for mode, tile in zip(MODES, tiles, strict=True)
        )
        answers[ident] = dict(
            position=site,
            archive_cutoff_utc_ns=cutoff,
            tile_center_errors_km={
                mode: distance_km(tile["center"], site)
                for mode, tile in zip(MODES, tiles, strict=True)
            },
        )
    return (
        jobs,
        answers,
        dict(
            generator_snapshot_sha256=scene.CATALOG_SHA256,
            latest_collection_utc_ns=received,
            snapshots=sorted(archival, key=lambda v: (v["collected_utc_ns"], v["sha256"])),
        ),
    )


def replay(scratch, report, cpus, seed_hex):
    parity = json.loads((report / "roof-parity.json").read_bytes())
    if not parity["identical"]:
        raise ValueError("authentic roof parity must hold before transfer")
    source = source_lock()
    if source != json.loads((report / "source-lock.json").read_bytes()):
        raise ValueError("the portable adapter differs from its parity-checked source")
    save_json(
        report / "synthetic-source-lock.json",
        dict(solver=source, generator=checksum(scene.__file__), adapter=checksum(__file__)),
    )
    seed = secrets.token_bytes(32) if seed_hex is None else bytes.fromhex(seed_hex)
    if len(seed) != 32:
        raise ValueError("synthetic draw requires a 32-byte seed")
    jobs, answers, history = new_scenes(seed)
    save_json(report / "authentic-history.json", history)
    kernel = scratch / "orbit_projector.so"
    orbit_projector.compile_kernel(kernel)

    def sequence(cpu, rows):
        return [portable_trial(*row, kernel, cpu, CASE_S) for row in rows]

    block = len(MODES)
    by_site = [jobs[i : i + block] for i in range(0, len(jobs), block)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        completed = [
            pool.submit(sequence, cpu, group if i % 2 == 0 else list(reversed(group)))
            for i, (cpu, group) in enumerate(zip(cpus, by_site, strict=True))
        ]
        rows = [r for job in completed for r in job.result()]
    if source_lock() != source:
        raise ValueError("portable receiver source changed during the prospective trial")
    seals = {}
    for mode in MODES:
        path = report / f"{mode}.jsonl.gz"
        write(
            path,
            gzip.compress(
                b"".join(encoded(r) + b"\n" for r in rows if r["mode"] == mode),
                mtime=0,
            ),
        )
        seals[mode] = checksum(path)
    save_json(report / "prediction-lock.json", seals)
    save_json(report / "synthetic-labels.json", dict(seed_hex=seed.hex(), captures=answers))


def score(report):
    lock = json.loads((report / "prediction-lock.json").read_bytes())
    runs = {}
    for mode in MODES:
        path = report / f"{mode}.jsonl.gz"
        if checksum(path) != lock[mode]:
            raise ValueError("transfer inference is not sealed")
        with gzip.open(path, "rt") as stream:
            runs[mode] = list(map(json.loads, stream))
        if len(runs[mode]) != len(SITE_BOXES):
            raise ValueError("expected both frozen draw cases")
    labels = json.loads((report / "synthetic-labels.json").read_bytes())["captures"]
    rows, summary = [], {}
    for a, b in zip(*runs.values(), strict=True):
        for key in ("id", "document_sha256", "history_sha256"):
            if a[key] != b[key]:
                raise ValueError(
                    "matched and omitted cases do not share the same capture and history"
                )
    for mode, results in runs.items():
        group = []
        for row in results:
            ident, result = row["id"], row["result"]
            validate_result(result)
            label = labels[ident]
            for arm in ARMS:
                rec = result.get("arms", {}).get(arm, {})
                point = rec["latlon"]
                group.append(
                    dict(
                        id=ident,
                        mode=mode,
                        arm=arm,
                        status=result["status"],
                        worker_wall_s=row["worker_wall_s"],
                        center_error_km=label["tile_center_errors_km"][mode],
                        position_error_km=distance_km(point, label["position"]),
                        false_fix=mode == "omitted-tile" and point is not None,
                        conditional_rf_rms_hz=rec.get("rf_rms_hz"),
                    )
                )
        rows.extend(group)
        summary[mode] = {
            arm: {
                "attempts": len(results),
                "positions": distribution(r["position_error_km"] for r in group if r["arm"] == arm),
                "false_fixes": sum(r["false_fix"] for r in group if r["arm"] == arm),
                "conditional_rf_rms_hz": distribution(
                    r["conditional_rf_rms_hz"] for r in group if r["arm"] == arm
                ),
            }
            for arm in ARMS
        }
    csv_file(report / "synthetic-scores.csv", rows)
    save_json(report / "summary.json", summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, default=Path("/tmp/leo-portable-v5-transfer"))
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--cpus", type=int, nargs=2, default=(4, 5))
    parser.add_argument("--seed-hex")
    parser.add_argument("--score", action="store_true")
    args = parser.parse_args()
    scratch, report = local_output(args.scratch), local_output(args.report)
    if args.score:
        score(report)
    else:
        if len(set(args.cpus)) != 2 or not set(args.cpus) <= os.sched_getaffinity(0):
            parser.error("choose two distinct available CPUs")
        scratch.mkdir(parents=True, exist_ok=True)
        replay(scratch, report, args.cpus, args.seed_hex)


if __name__ == "__main__":
    main()
