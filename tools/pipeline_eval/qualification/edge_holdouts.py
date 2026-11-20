"""Replay the frozen compact support and interior decisions across new sites."""

import argparse
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

import numpy as np

from ..__main__ import encoded, local_output, save_json
from ..scoring import distance_km
from ..variants import compact_tile_interior as edge
from . import transfer_budget as worker
from .fresh_scenes import _destination, _new, _read, _sha

REPORT = worker.REPORT.parents[1] / "integration/edge-holdouts"
CPUS = (4, 5, 6, 7)
CASE_S = 115
PANEL_S = 570
METHOD = "v5_secant_transfer_interior"
ROLES = ("original", "near-inside", "near-outside", "far-outside")
SITES = (
    ((58.0, -93.0), (0.35, 0.75)),
    ((-3.0, 117.0), (1.1, 1.7)),
    ((-43.0, 172.0), (2.3, 2.9)),
)
INPUTS = worker.scenes.inputs


def prior_context():
    prior = worker.compact.prior.REPORT
    old = INPUTS._prior_sites()
    old.update(tuple(r["latlon"]) for r in _read(prior / "truth.json").values() if r["latlon"])
    draws = list(_read(prior / "draws.json").values())
    for directory in (worker.REPORT, worker.REPORT / "interior-guard"):
        truth = _read(directory / "released-truth.json")
        draw = _read(directory / "fresh-draw.json")
        old.add(tuple(truth["location"]))
        draws.append(dict(causal=draw["source"], trajectory=truth["trajectory"]))
    safe = _read(prior.parents[1] / "portable-v5/synthetic-labels.json")["captures"]
    old.update(tuple(r["position"]) for r in safe.values())
    used = {r[key]["sha256"] for r in draws for key in ("causal", "trajectory")}
    return old, used


def offers(site, rng, near_range):
    near = rng.uniform(*near_range)
    bearing = rng.uniform(0, 2 * np.pi)
    legal = _destination(site, rng.uniform(8, 10), rng.uniform(0, 2 * np.pi))
    ident = [rng.bytes(12).hex() for _ in ROLES]
    return (
        INPUTS._tile(ident[0], legal),
        INPUTS._at_margin(ident[1], site, bearing, near),
        INPUTS._at_margin(ident[2], site, bearing, -near),
        INPUTS._at_margin(ident[3], site, rng.uniform(0, 2 * np.pi), -rng.uniform(35, 65)),
    )


def draw(root, seeds):
    old, used = prior_context()
    pool, receipts = INPUTS.empirical.donors()
    snapshots = INPUTS.snapshots()
    private, public = root / "private", root / "public"
    private.mkdir(mode=0o700)
    public.mkdir()
    for (center, band), seed in zip(SITES, seeds, strict=True):
        rng = np.random.default_rng(int.from_bytes(seed, "big"))
        for _ in range(12):
            site = tuple(rng.uniform(-2, 2, size=2) + center)
            distance = min(distance_km(site, p) for p in old)
            if distance >= 1_000:
                break
        else:
            raise ValueError("site disjointness draw exhausted")
        old.add(site)
        for _ in range(8):
            early, late, anchor = INPUTS._history(snapshots, used, rng)
            bank = INPUTS._true_bank(
                INPUTS._tle(early), INPUTS._tle(late), anchor, late["received"]
            )
            try:
                probes, counter, info = INPUTS.cold._generate_capture(bank, anchor, site, rng)
            except ValueError as error:
                if str(error) != "insufficient visible causal orbit opportunities":
                    raise
            else:
                break
        else:
            raise ValueError("orbital visibility draw exhausted")
        used.update((early["sha256"], late["sha256"]))
        disturbances = INPUTS.empirical._inject(
            dict(probes=probes, first_counter=counter), pool, rng
        )
        capture = rng.bytes(12).hex()
        tiles = offers(site, rng, band)
        raw = encoded(INPUTS._native(capture, anchor, counter, probes))
        INPUTS.cold._new(public / f"{capture}.native.json", raw)
        _new(
            public / f"{capture}.json",
            dict(
                capture_id=capture,
                packet_sha256=INPUTS.cold._sha(raw),
                source=early,
                cutoff=anchor,
                tiles=tiles,
                donor_receipts=receipts,
            ),
        )
        _new(
            private / f"{capture}.json",
            dict(
                location=site,
                roles={r["id"]: k for k, r in zip(ROLES, tiles, strict=True)},
                seed_hex=seed.hex(),
                trajectory=late,
                emitters=info["emitters"],
                perturbed_lanes=disturbances,
                nearest_prior_km=distance,
            ),
        )
        yield capture


def jobs(root, captures):
    public = root / "public"
    for capture in captures:
        case = _read(public / f"{capture}.json")
        native = public / f"{capture}.native.json"
        if _sha(native) != case["packet_sha256"]:
            raise ValueError("synthetic input binding changed")
        earlier = case["source"]["sha256"]
        history, objects, inventory = worker.compact.history_at(case["cutoff"], earlier)
        doc = worker.compact.complete_native(_read(native))
        rows = [
            worker.compact.bound_job(
                dict(
                    id=tile["id"],
                    capture_id=capture,
                    native_sha256=_sha(native),
                    catalog_sha256=earlier,
                ),
                doc,
                tile,
                history,
                objects,
            )
            for tile in case["tiles"]
        ]
        yield rows, inventory


def sources(output):
    main = _read(worker.REPORT / "policy-lock.json")
    upper = _read(worker.REPORT / "interior-guard/source-lock.json")
    frozen = (
        Path(edge.__file__),
        Path(worker.rule.__file__),
        worker.WORKER,
        Path(worker.compact.v5_secant_fit.__file__),
        Path(worker.__file__),
    )
    if any(_sha(path) != (main.get(str(path), upper.get(path.name))) for path in frozen):
        raise ValueError("frozen solver version changed")
    return worker.compact.portable.source_lock() | {
        p.name: _sha(p)
        for p in (
            *frozen,
            output / "PROTOCOL.md",
            Path(__file__),
            Path(INPUTS.__file__),
            Path(INPUTS.cold.__file__),
            Path(INPUTS.empirical.__file__),
        )
    }


def replay(root, output):
    started = perf_counter()
    save_json(output / "source-lock.json", sources(output))
    captures = list(draw(root, [secrets.token_bytes(32) for _ in SITES]))
    panels = list(jobs(root, captures))
    records = [(j, "gate") for rows, _ in panels for j in rows]
    records.extend((rows[-1], "control") for rows, _ in panels)
    # Start the full far comparisons concurrently with the first three centre fits.
    records = records[-3:] + records[:-3]
    plan = [dict(j[0], mode=mode) for j, mode in records]
    save_json(output / "requests.json", plan)
    save_json(
        output / "causal-history.json", {c: p[1] for c, p in zip(captures, panels, strict=True)}
    )
    committed = {
        str(f.relative_to(root)): _sha(f)
        for d in ("public", "private")
        for f in sorted((root / d).iterdir())
    }
    save_json(output / "input-lock.json", committed)
    kernel = root / "projector.so"
    worker.compact.orbit_projector.compile_kernel(kernel)

    def run(cpu, tasks):
        out = []
        for j, mode in tasks:
            remaining = int(PANEL_S - (perf_counter() - started))
            if remaining < 15:
                missing = worker.compact.portable_v5.unavailable("batch window expired")
                out.append(dict(j[0], mode=mode, result=missing, trace=[], wall_s=None, cpu=cpu))
            else:
                row = worker.run_one(j, kernel, cpu, mode, min(CASE_S, remaining))
                if mode == "gate":
                    row["terminal_result"] = edge.guard(row["result"], row["tile"])
                out.append(dict(row, mode=mode))
        return out

    with ThreadPoolExecutor(max_workers=4) as pool:
        batches = pool.map(run, CPUS, [records[i::4] for i in range(4)])
        result = [r for b in batches for r in b]
    if any(_sha(root / name) != sha for name, sha in committed.items()):
        raise ValueError("sealed inputs changed during inference")
    filename = "predictions.json"
    save_json(output / filename, result)
    evidence = (
        filename,
        "source-lock.json",
        "requests.json",
        "causal-history.json",
        "input-lock.json",
    )
    save_json(
        output / "prediction-lock.json",
        dict(
            files={name: _sha(output / name) for name in evidence},
            wall_s=perf_counter() - started,
        ),
    )
    for name, folder in (("released-labels.json", "private"), ("public-captures.json", "public")):
        save_json(output / name, {c: _read(root / folder / f"{c}.json") for c in captures})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scratch", type=Path)
    parser.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args()
    if not set(CPUS) <= os.sched_getaffinity(0):
        parser.error("pin the replay to the four authorized cores")
    replay(local_output(args.scratch), local_output(args.out))
