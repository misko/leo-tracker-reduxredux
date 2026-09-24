#!/usr/bin/env python3
import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import multiprocessing
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parents[2]
HERE = Path(__file__).parent
CLOCK = ROOT / "reports/2026_09_24_shared_clock_grid/run.py"
DATA = HERE / "dataset.json"
SPACINGS = (5.0, 2.5, 1.25, 0.625, 0.3125, 0.15625)
TAU_LEVELS = {5.0, 1.25, 0.3125, 0.15625}
MISSING = "scan-hop-6cd2560365a058bc"
CACHE_ROOTS = {
    "20260921_00": Path("/tmp/leo-long-training-cache-full8h"),
    "20260921_16": Path("/tmp/leo-long-training-cache-second8h"),
    "20260922_08": Path("/tmp/leo-frozen-validation-cache"),
    "20260921_08": Path("/tmp/leo-frozen-validation-cache"),
    "20260922_00": Path("/tmp/leo-final-test-global-epoch-cache"),
}


def load(path, name):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    sys.modules[name] = m
    s.loader.exec_module(m)
    return m


def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verified_json(path):
    path = Path(path)
    seal = path.with_suffix(".sha256")
    if not seal.exists() or seal.read_text().strip().split()[0] != digest(path).split(":", 1)[1]:
        raise ValueError(f"bad or missing seal: {path}")
    return json.loads(path.read_text())


def seed_path(case):
    cid = case["case_id"]
    if cid.startswith("train_20260921_00_1") and cid.endswith("_1"):
        return ROOT / "reports/2026_09_23_long_training_search/results/inference.json"
    if cid.startswith("train_20260921_00_") and case["scan_count"] in (6, 16):
        return ROOT / "reports/2026_09_23_long_training_search_multi/results/inference.json"
    if cid == "train_20260921_00_all":
        return ROOT / "reports/2026_09_23_long_training_full8h_position/results/inference.json"
    if cid.startswith("train_20260921_16_"):
        return ROOT / "reports/2026_09_23_long_second8h_training_baseline/results/inference.json"
    if cid.startswith("validation_"):
        return ROOT / "reports/2026_09_23_frozen_validation/baseline/inference.json"
    if cid.startswith("test_"):
        return ROOT / "reports/2026_09_23_final_test_global_epoch/baseline/inference.json"
    raise KeyError(cid)


def seed_search(case, prior):
    cid = case["case_id"]
    count = case["scan_count"]
    if cid == "test_20260922_00_all":
        return None
    p = verified_json(seed_path(case))
    if "session_id" in p and [p["session_id"]] != case["session_ids"]:
        raise ValueError(f"seed singleton mismatch: {cid}")
    if "session_ids" in p and p["session_ids"][:count] != case["session_ids"]:
        raise ValueError(f"seed cohort mismatch: {cid}")
    if cid.startswith(("validation_", "test_")):
        iso = next(
            g["utc_8h_start"]
            for g in json.loads(DATA.read_text())["groups"]
            if g["group_id"] == case["group_id"]
        )
        group = next(g for g in p["groups"] if g["utc_8h_start"] == iso)
        if group["session_ids"][:count] != case["session_ids"]:
            raise ValueError(f"seed group cohort mismatch: {cid}")
    if cid == "train_20260921_00_1":
        return next(x for x in p["searches"] if x["prior"] == prior)
    if cid.startswith("train_20260921_00_") and count in (6, 16):
        v = next(x for x in p["views"] if x["scan_count"] == count)
        return next(x for x in v["searches"] if x["prior"] == prior)
    if cid == "train_20260921_00_all":
        return next(x for x in p["searches"] if x["prior"] == prior)
    if cid.startswith("train_20260921_16_"):
        return next(
            x["search"] for x in p["arms"] if x["scan_count"] == count and x["prior"] == prior
        )
    if cid.startswith("validation_"):
        iso = next(
            g["utc_8h_start"]
            for g in json.loads(DATA.read_text())["groups"]
            if g["group_id"] == case["group_id"]
        )
        return next(
            x["search"]
            for x in p["arms"]
            if x["group"] == iso and x["scan_count"] == count and x["prior"] == prior
        )
    if cid.startswith("test_"):
        return next(
            x["search"] for x in p["arms"] if x["scan_count"] == count and x["prior"] == prior
        )
    raise KeyError(cid)


def make_engine(case):
    mod = load(CLOCK, "ds1_clock_engine")
    engine = mod.Engine.__new__(mod.Engine)
    engine.search = load(mod.SEARCH, "ds1_search")
    engine.sessions = []
    engine.bindings = []
    root = CACHE_ROOTS[case["group_id"]]
    source = verified_json(seed_path(case))
    expected = {row["session_id"]: row for row in source.get("bindings", {}).get("sessions", [])}
    if not expected and "session_id" in source:
        expected[source["session_id"]] = {
            "receipt": source["bindings"]["receipt"],
            "cache": source["bindings"]["cache"],
        }
    if not expected and case["partition"] in ("validation", "test"):
        receipt_bundle = seed_path(case).parents[1] / "cache_receipts.json"
        expected = {
            row["session_id"]: row for row in json.loads(receipt_bundle.read_text())["rows"]
        }
    for sid in case["session_ids"]:
        receipt_path = root / sid / "cache_receipt.json"
        cache_path = root / sid / "state_cache.npz"
        if not receipt_path.exists() or not cache_path.exists():
            raise FileNotFoundError(sid)
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("session_id") != sid:
            raise ValueError(f"receipt session mismatch: {sid}")
        if not str(receipt.get("candidate_policy", "")).startswith(
            "all causal non-debris STARLINK"
        ):
            raise ValueError(f"candidate policy mismatch: {sid}")
        current = {"receipt": digest(receipt_path), "cache": digest(cache_path)}
        if sid not in expected or any(current[k] != expected[sid][k] for k in current):
            raise ValueError(f"cache provenance mismatch: {sid}")
        if receipt.get("bindings", {}).get("state_cache") != current["cache"]:
            raise ValueError(f"receipt/cache cross-check failed: {sid}")
        with np.load(cache_path, allow_pickle=False) as a:
            arrays = {k: a[k] for k in a.files}
        if (
            len(arrays["candidate_id"]) != arrays["position_ecef_km"].shape[0]
            or arrays["position_ecef_km"].shape != arrays["velocity_ecef_km_s"].shape
        ):
            raise ValueError(f"cache shape mismatch: {sid}")
        tracks = []
        for t in receipt["prepared_evidence"]["tracks"]:
            times = np.asarray(t["times_s"], float)
            mask = np.asarray(t["training_mask"], bool)
            if np.ptp(times) >= 3:
                if not mask.any() or not (~mask).any():
                    raise ValueError("empty mask")
                tracks.append(
                    {
                        "track_id": t["track_id"],
                        "times": times,
                        "measured": np.asarray(t["measured_hz"], float),
                        "train": mask,
                        "weight": int(len(np.unique(np.floor(times)))),
                    }
                )
        grid = arrays["receive_plus_tau_offset_ns"].astype(float) / 1e9
        all_times = np.concatenate([t["times"] for t in tracks])
        if grid[0] > all_times.min() - 5 or grid[-1] < all_times.max() + 5:
            raise ValueError(f"cache lacks five-second margin: {sid}")
        engine.sessions.append(
            {
                "session_id": sid,
                "candidate_ids": arrays["candidate_id"],
                "grid": grid,
                "position": arrays["position_ecef_km"],
                "velocity": arrays["velocity_ecef_km_s"],
                "tracks": tracks,
            }
        )
        engine.bindings.append({"session_id": sid, **current})
    return mod, engine


def key(lat, lon, tau):
    return (round(float(lat), 10), round(float(lon), 10), round(float(tau), 10))


def choose(rows, model):
    eligible = [r for r in rows.values() if (r["tau_s"] == 0 if model == "baseline" else True)]
    return min(
        eligible,
        key=lambda r: (
            r["training_capped_loss"],
            abs(r["tau_s"]),
            r["tau_s"],
            r["latitude_deg"],
            r["longitude_deg"],
        ),
    )


def run_arm(task):
    case, prior = task
    started = time.monotonic()
    outdir = HERE / "inference"
    outdir.mkdir(exist_ok=True)
    path = outdir / f"{case['case_id']}__{prior}.json"
    if path.exists() or path.with_suffix(".sha256").exists():
        raise FileExistsError(f"refusing overwrite: {path}")
    if MISSING in case["session_ids"]:
        out = {
            "schema": "ds1-paired-arm/v1",
            "complete": True,
            "case_id": case["case_id"],
            "prior": prior,
            "failure": {
                "session_id": MISSING,
                "reason": (
                    "missing counter-continuity authority/cache; exact full TEST cohort ineligible"
                ),
            },
            "bindings": {
                "protocol": digest(HERE / "PROTOCOL.md"),
                "dataset": digest(DATA),
                "source": digest(__file__),
            },
        }
        path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
        path.with_suffix(".sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "\n")
        return {
            "case_id": case["case_id"],
            "prior": prior,
            "failure": True,
            "elapsed_s": time.monotonic() - started,
        }
    mod, engine = make_engine(case)
    search = seed_search(case, prior)
    seed = search["selected"]
    prior_def = json.loads(DATA.read_text())["priors"][prior]
    rows = {}
    levels = []
    if (
        engine.search.haversine_km(prior_def[:2], (seed["latitude_deg"], seed["longitude_deg"]))
        > prior_def[2] + 1e-9
    ):
        raise ValueError("seed outside frozen prior")

    def score(lat, lon, taus, stage):
        pending = [float(t) for t in taus if key(lat, lon, t) not in rows]
        if not pending:
            return
        losses, _, _ = engine.profile(lat, lon, np.asarray(pending), False, False)
        for tau, loss in zip(pending, losses, strict=True):
            rows[key(lat, lon, tau)] = {
                "latitude_deg": float(lat),
                "longitude_deg": float(lon),
                "tau_s": tau,
                "training_capped_loss": float(loss),
                "stage": stage,
            }

    lat, lon = seed["latitude_deg"], seed["longitude_deg"]
    score(lat, lon, [0], "seed_tau0")
    reproduced = np.sqrt(rows[key(lat, lon, 0)]["training_capped_loss"]) * 800
    if not np.isclose(reproduced, seed["objective_rmse_hz"], rtol=0, atol=1e-7):
        raise ValueError(f"seed tau0 parity failed: {reproduced} != {seed['objective_rmse_hz']}")
    coarse = np.arange(-5.0, 5.1, 1.0)
    score(lat, lon, coarse, "seed_tau_coarse")
    current = choose(rows, "shared")
    fine = np.unique(
        np.append(
            np.arange(max(-5, current["tau_s"] - 1), min(5, current["tau_s"] + 1) + 0.001, 0.25),
            [0, current["tau_s"]],
        )
    )
    score(lat, lon, fine, "seed_tau_fine")
    for spacing in SPACINGS:
        baseline, current = choose(rows, "baseline"), choose(rows, "shared")
        points = set()
        for winner in (baseline, current):
            for de in (-spacing, 0, spacing):
                for dn in (-spacing, 0, spacing):
                    plat, plon = engine.search.offset_coordinate(
                        (winner["latitude_deg"], winner["longitude_deg"]), de, dn
                    )
                    if (
                        engine.search.haversine_km(prior_def[:2], (plat, plon))
                        <= prior_def[2] + 1e-9
                    ):
                        points.add((plat, plon))
        for plat, plon in sorted(points):
            score(plat, plon, [0, current["tau_s"]], f"space_{spacing}")
        if spacing in TAU_LEVELS:
            current = choose(rows, "shared")
            taus = np.unique(
                np.append(
                    np.arange(
                        max(-5, current["tau_s"] - 0.5),
                        min(5, current["tau_s"] + 0.5) + 0.0001,
                        0.1,
                    ),
                    [0, current["tau_s"]],
                )
            )
            score(current["latitude_deg"], current["longitude_deg"], taus, f"tau_{spacing}")
        levels.append(
            {
                "spacing_km": spacing,
                "pair_count": len(rows),
                "baseline": choose(rows, "baseline"),
                "shared": choose(rows, "shared"),
            }
        )
    baseline, current = choose(rows, "baseline"), choose(rows, "shared")
    if any(
        levels[i]["baseline"]["training_capped_loss"]
        > levels[i - 1]["baseline"]["training_capped_loss"] + 1e-15
        or levels[i]["shared"]["training_capped_loss"]
        > levels[i - 1]["shared"]["training_capped_loss"] + 1e-15
        for i in range(1, len(levels))
    ):
        raise AssertionError("incumbent worsened")
    track_count = sum(len(s["tracks"]) for s in engine.sessions)
    obs_count = sum(len(t["times"]) for s in engine.sessions for t in s["tracks"])
    occupied = sum(t["weight"] for s in engine.sessions for t in s["tracks"])
    out = {
        "schema": "ds1-paired-arm/v1",
        "complete": True,
        "case_id": case["case_id"],
        "partition": case["partition"],
        "group_id": case["group_id"],
        "scan_count": case["scan_count"],
        "prior": prior,
        "models": {"baseline": baseline, "shared_time": current},
        "visited_pairs": list(rows.values()),
        "levels": levels,
        "track_count": track_count,
        "observation_count": obs_count,
        "occupied_second_denominator": occupied,
        "seed_tau0_reproduced_rmse_hz": reproduced,
        "elapsed_s": time.monotonic() - started,
        "held_used_for_fit": False,
        "truth_used_for_fit": False,
        "session_bindings": engine.bindings,
        "bindings": {
            "protocol": digest(HERE / "PROTOCOL.md"),
            "dataset": digest(DATA),
            "source": digest(__file__),
            "clock_engine": digest(CLOCK),
            "search_engine": digest(mod.SEARCH),
            "seed_inference": digest(seed_path(case)),
        },
    }
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    path.with_suffix(".sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "\n")
    return {
        "case_id": case["case_id"],
        "prior": prior,
        "failure": False,
        "pair_count": len(rows),
        "elapsed_s": time.monotonic() - started,
    }


def benchmark():
    data = json.loads(DATA.read_text())
    wanted = [
        ("train_20260921_16_1", "sacramento"),
        ("train_20260921_16_6", "sacramento"),
        ("train_20260921_16_16", "sacramento"),
        ("train_20260921_16_all", "sacramento"),
    ]
    rows = []
    for cid, prior in wanted:
        case = next(x for x in data["cases"] if x["case_id"] == cid)
        mod, engine = make_engine(case)
        seed = seed_search(case, prior)["selected"]
        begun = time.monotonic()
        engine.profile(seed["latitude_deg"], seed["longitude_deg"], np.array([0.0]), False, False)
        rows.append(
            {
                "case_id": cid,
                "scan_count": case["scan_count"],
                "one_pair_s": time.monotonic() - begun,
            }
        )
    out = {
        "schema": "ds1-benchmark/v1",
        "rows": rows,
        "projected_pair_budget_per_arm": 172,
        "workers": 16,
        "bindings": {
            "source": digest(__file__),
            "protocol": digest(HERE / "PROTOCOL.md"),
            "dataset": digest(DATA),
        },
    }
    (HERE / "benchmark.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps(out, indent=2))


def main():
    if (HERE / "inference_index.json").exists() or (HERE / "inference").exists():
        raise FileExistsError("refusing to overwrite inference outputs")
    if (HERE / "dataset.sha256").read_text().strip().split()[0] != digest(DATA).split(":", 1)[1]:
        raise ValueError("dataset seal mismatch")
    data = json.loads(DATA.read_text())
    tasks = [(c, p) for c in data["cases"] for p in data["priors"]]
    tasks.sort(key=lambda x: x[0]["scan_count"], reverse=True)
    begun = time.monotonic()
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=16, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        results = []
        for r in pool.map(run_arm, tasks, chunksize=1):
            results.append(r)
            print("completed", r["case_id"], r["prior"], flush=True)
    out = {
        "schema": "ds1-run/v1",
        "complete": True,
        "arm_count": len(results),
        "results": results,
        "elapsed_s": time.monotonic() - begun,
        "bindings": {
            "protocol": digest(HERE / "PROTOCOL.md"),
            "dataset": digest(DATA),
            "source": digest(__file__),
        },
    }
    path = HERE / "inference_index.json"
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    (HERE / "inference_index.sha256").write_text(
        hashlib.sha256(path.read_bytes()).hexdigest() + "\n"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--benchmark", action="store_true")
    a = p.parse_args()
    benchmark() if a.benchmark else main()
