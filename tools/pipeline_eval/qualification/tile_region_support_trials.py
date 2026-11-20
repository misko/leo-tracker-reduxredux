"""Qualify conditional geographic support on held Doppler observations."""

import argparse
import gzip
import hashlib
import json
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from ..variants import orbit_projector, portable_gate, portable_gate_coverage, tile_region_support
from . import portable_gate_trials as prior
from .portable_v5_transfer import new_scenes

METHOD = tile_region_support.METHOD
WORKER = Path(__file__).with_name("tile_region_support_worker.py")
OUT = ROOT / "reports/2026_11_19_receiver_screening/factors/region-support"
CAP_S = 195
REPLAYS = (("coverage", "omitted-tile"), ("halo", "matched-tile"))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_rows(path):
    return list(map(json.loads, gzip.decompress(path.read_bytes()).splitlines()))


def source():
    paths = (
        Path(__file__),
        WORKER,
        Path(portable_gate_coverage.__file__),
        Path(tile_region_support.__file__),
    )
    return dict(prior=prior.lock(), files={p.name: prior.checksum(p) for p in paths})


def edge_offer(site, rng):
    """Construct a containing tile with true clearance 1.5 km from one face."""
    east, north = rng.permutation([11.0, float(rng.uniform(0, 5))]) * rng.choice([-1, 1], size=2)
    lat = site[0] - north / 111.0
    lon = site[1] - east / (111.32 * np.cos(np.deg2rad(lat)))
    return dict(center=[lat, lon], width_km=25.0)


def fresh(seed):
    jobs, labels, history = new_scenes(seed)
    rng = np.random.default_rng(int.from_bytes(seed, "big") + 1)
    out = []
    for a, b in zip(jobs[::2], jobs[1::2], strict=True):
        ident, _, doc, _, rows, files = a
        edge = (ident, "edge-tile", doc, edge_offer(labels[ident]["position"], rng), rows, files)
        out.append((a, b, edge))
    return out, labels, history


def replays():
    entries, labels = [], {}
    for study, mode in REPLAYS:
        folder = prior.REPORT / study
        lock = json.loads((folder / "prediction-lock.json").read_bytes())
        assert prior.checksum(folder / "fresh.jsonl.gz") == lock["files"]["fresh.jsonl.gz"]
        (row,) = [r for r in read_rows(folder / "fresh.jsonl.gz") if r["mode"] == mode]
        label = json.loads((folder / "labels.json").read_bytes())
        jobs, _, _ = new_scenes(bytes.fromhex(label["seed_hex"]))
        job = next(j for j in jobs if j[:2] == (row["id"], mode))
        entries.append(job)
        labels[row["id"]] = dict(label["fresh"][row["id"]], previous=row, previous_study=study)
    return entries, labels


def worker(cpu, job, kernel, cohort):
    ident, mode, document, offer, stamps, files = job
    data = encoded(dict(document=document, tile=offer, history=stamps))
    command = prior.worker_command(
        cpu, files, kernel, WORKER, (portable_gate, portable_gate_coverage, tile_region_support)
    )
    out, err, state, elapsed = prior.invoke(command, data, CAP_S)
    if state == "complete":
        result = json.loads(out)
    else:
        reason = err.decode(errors="replace")[-2400:] if state == "failed" else "wall cap reached"
        result = dict(
            status=state,
            boundary=tile_region_support.BOUNDARY,
            reason=reason or state,
            arms={a: dict(latlon=None) for a in ARMS},
            metrics={},
        )
    validate_result(result)
    print(cohort, ident, mode, result["status"], round(elapsed, 2), flush=True)
    return dict(
        id=f"{cohort}-{ident}-{mode}",
        capture_id=ident,
        mode=mode,
        cohort=cohort,
        offer=offer,
        method=METHOD,
        result=result,
        input_sha256=sha(data),
        document_sha256=sha(encoded(document)),
        history_sha256=sha(encoded(stamps)),
        worker_wall_s=elapsed,
        cpu=cpu,
    )


def infer(scratch, report, cpus, seed_hex):
    lock = source()
    save_json(report / "source-lock.json", lock)
    seed = bytes.fromhex(seed_hex) if seed_hex else secrets.token_bytes(32)
    sites, labels, history = fresh(seed)
    old, old_labels = replays()
    save_json(report / "authentic-history.json", history)
    kernel = scratch / "projector.so"
    orbit_projector.compile_kernel(kernel)

    def execute(cpu, site, replay):
        queries = [(case, "fresh") for case in site] + [(replay, "replay")]
        return [worker(cpu, case, kernel, cohort) for case, cohort in queries]

    with ThreadPoolExecutor(max_workers=2) as pool:
        queued = [
            pool.submit(execute, cpu, site, replay)
            for cpu, site, replay in zip(cpus, sites, old, strict=True)
        ]
    rows = [result for t in queued for result in t.result()]
    if source() != lock:
        raise ValueError("scientific sources changed after the blind draw")
    write(report / "raw-positions.jsonl.gz", prior.compressed_rows(rows))
    save_json(
        report / "prediction-lock.json",
        dict(raw_sha256=prior.checksum(report / "raw-positions.jsonl.gz")),
    )
    save_json(report / "labels.json", dict(seed_hex=seed.hex(), fresh=labels, replay=old_labels))


def score(report):
    lock = json.loads((report / "prediction-lock.json").read_bytes())
    assert prior.checksum(report / "raw-positions.jsonl.gz") == lock["raw_sha256"]
    rows = read_rows(report / "raw-positions.jsonl.gz")
    labels = json.loads((report / "labels.json").read_bytes())
    scores = []
    for group in ("fresh", "replay"):
        selected = [r for r in rows if r["cohort"] == group]
        assert len(selected) == (6 if group == "fresh" else 2)
        queries, comparators = [], []
        identifiers = list(labels[group])
        for row in selected:
            ident, mode = row["capture_id"], row["mode"]
            label = labels[group][ident]
            binding = {k: row[k] for k in ("input_sha256", "document_sha256", "history_sha256")}
            if previous := label.get("previous"):
                assert all(previous[k] == v for k, v in binding.items())
                comparators.append(
                    dict(
                        previous,
                        id=row["id"],
                        prior_method=previous["method"],
                        method="prior_region_gate",
                    )
                )
            title = (
                f"Site {identifiers.index(ident) + 1}"
                if group == "fresh"
                else label["previous_study"]
            )
            condition = {"matched-tile": "present", "edge-tile": "edge", "omitted-tile": "missing"}[
                mode
            ]
            queries.append(
                dict(
                    id=row["id"],
                    condition=condition,
                    recording=title,
                    truth=label["position"],
                    bindings=binding,
                )
            )
            for variant in (row, *([previous] if previous else [])):
                for arm, a in variant["result"]["arms"].items():
                    scores.append(
                        dict(
                            query=row["id"],
                            arm=arm,
                            condition=condition,
                            cohort=group,
                            method=variant["method"],
                            status=variant["result"]["status"],
                            position_error_km=distance_km(a["latlon"], label["position"]),
                            rf_rms_hz=a.get("rf_rms_hz"),
                            runtime_s=variant["worker_wall_s"],
                            gate=row["result"]["metrics"].get("geographic_gate", {})
                            if variant is row
                            else {},
                        )
                    )
        positions = f"{group}-positions.jsonl.gz"
        query_file = f"{group}-queries.json"
        write(report / positions, prior.compressed_rows(selected))
        save_json(report / query_file, dict(queries=queries))
        files = [positions, query_file]
        if comparators:
            baseline = f"{group}-stock.jsonl.gz"
            write(report / baseline, prior.compressed_rows(comparators))
            files.append(baseline)
        save_json(
            report / f"{group}-figure-lock.json",
            dict(
                cases=[r["id"] for r in selected],
                files={n: prior.checksum(report / n) for n in files},
            ),
        )
    save_json(report / "scores.json", dict(rows=scores))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=OUT)
    parser.add_argument("--cpus", type=int, nargs=2, default=(0, 7))
    parser.add_argument("--seed-hex")
    parser.add_argument("--score", action="store_true")
    args = parser.parse_args()
    scratch, report = local_output(args.scratch), local_output(args.report)
    if args.score:
        score(report)
    else:
        if len(set(args.cpus)) != 2 or not set(args.cpus) <= os.sched_getaffinity(0):
            parser.error("choose two distinct available CPUs")
        scratch.mkdir(exist_ok=True, parents=True)
        infer(scratch, report, args.cpus, args.seed_hex)


if __name__ == "__main__":
    main()
