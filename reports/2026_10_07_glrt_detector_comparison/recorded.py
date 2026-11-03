"""Bounded, unlabeled recorded-IQ comparison; no production changes or RF collection."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATASET = ROOT / "reports/2026_09_26_ds5_server_eval/dataset"
OUTPUT = HERE / "recorded"
SPLITS = ("dev", "validation", "holdout")
RATES = (2_500_000, 5_000_000, 7_500_000, 10_000_000)
CONFIG = {
    "selection": "first two visits by visit_index per real split/rate",
    "training_selection": "third and fourth dev visits per rate, both RX, first20ms",
    "windows_start_ms": [0, 40], "window_ms": 20, "receivers": [0, 1],
    "coarse_cfo_hz": list(range(-400_000, 400_001, 80_000)),
    "candidate_count": 8, "epoch_separation_samples": 20,
    "coarse_cfo_separation_hz": 80_000, "symbols": list(range(2, 66)),
    "fft_size": 512, "symbol_step_s": 4.4e-6, "shrinkage": 0.25,
    "consistency_cfo_tolerance_hz": 5_000,
    "consistency_epoch_tolerance_s": 4.4e-6,
    "truth_status": "unknown; no real ROC, false-alarm, or recall claims",
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()


def select_cases(payload: dict) -> tuple[list[dict], list[dict]]:
    groups = {(split, rate): [] for split in SPLITS for rate in RATES}
    sessions: dict[str, str] = {}
    for case in payload["cases"]:
        if case["origin"] != "real_ds5":
            continue
        key = (case["split"], case["rate_hz"])
        if key not in groups or case["truth_status"] != "unknown":
            raise ValueError("unexpected real case stratum/truth")
        session = case["session_id"]
        if session in sessions and sessions[session] != case["split"]:
            raise ValueError("session leaks across splits")
        sessions[session] = case["split"]
        groups[key].append(case)
    selected, training = [], []
    for (split, _), cases in groups.items():
        cases.sort(key=lambda c: (c["visit_index"], c["case_id"]))
        if len(cases) < 4:
            raise ValueError("incomplete fixed split/rate stratum")
        selected.extend(cases[:2])
        if split == "dev":
            training.extend(cases[2:4])
    assert_disjoint(selected, training)
    return selected, training


def assert_disjoint(selected: list[dict], training: list[dict]) -> None:
    if any(c["split"] != "dev" for c in training):
        raise ValueError("covariance training uses non-development data")
    if {c["case_id"] for c in selected} & {c["case_id"] for c in training}:
        raise ValueError("covariance training overlaps scored visits")
    for a in selected:
        for b in training:
            if a["session_id"] == b["session_id"] and max(
                a["source_start_counter"], b["source_start_counter"]
            ) < min(a["source_end_counter_exclusive"], b["source_end_counter_exclusive"]):
                raise ValueError("covariance training overlaps scored samples")


def load_iq(dataset: Path, case: dict) -> np.ndarray:
    path = (dataset / case["raw_npy"]["path"]).resolve()
    if not path.is_relative_to(dataset.resolve()):
        raise ValueError("IQ path escapes dataset")
    if digest(path) != case["raw_npy"]["sha256"]:
        raise ValueError(f"IQ hash mismatch: {case['case_id']}")
    values = np.load(path, allow_pickle=False, mmap_mode="r")
    if values.dtype != np.dtype("<i2") or values.shape != tuple(case["raw_npy"]["shape"]):
        raise ValueError("IQ geometry mismatch")
    return values


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def protocol(acquisition_mode: str) -> dict:
    if acquisition_mode not in ("coarse", "production"):
        raise ValueError("unknown acquisition mode")
    result = dict(CONFIG, acquisition_mode=acquisition_mode)
    if acquisition_mode == "production":
        acq, _, _ = numerical_helpers()
        result["production_acquisition_config"] = json.loads(json.dumps(asdict(
            acq.SymbolwiseAcquisitionConfig(maximum_probe_samples=max(RATES) // 50),
        )))
        result["maximum_probe_samples_per_rate"] = {str(r): r // 50 for r in RATES}
    return result


def freeze(dataset: Path, output: Path, acquisition_mode: str = "coarse") -> dict:
    path = dataset / "cases.json"
    selected, training = select_cases(json.loads(path.read_text()))
    frozen = {"config": protocol(acquisition_mode), "dataset_manifest_sha256": digest(path),
              "selected": selected, "training": training}
    output.mkdir(parents=True, exist_ok=True)
    target = output / "selection.json"
    if target.exists() and json.loads(target.read_text()) != frozen:
        raise ValueError("existing frozen selection/config differs")
    write_json(target, frozen)
    return frozen


def numerical_helpers():
    sys.path[:0] = [str(ROOT / "src"), str(HERE)]
    from leo.analysis.starlink import acquisition, pilot_methods, templates
    return acquisition, pilot_methods, templates


def energies(pm, rate: int, edge) -> tuple[np.ndarray, np.ndarray]:
    geometry = pm._conditioned_workspace_geometry(rate, edge)
    exact, control = np.zeros(300), np.zeros(300)
    for group in geometry.groups:
        exact[group.positions], control[group.positions] = group.exact_energy, group.control_energy
    return exact[:64], control[:64]


def matrices(pm, samples, rate, edge, epoch, cfo):
    workspace = pm._conditioned_correlation_workspace(
        samples, rate, epoch, cfo, edge=edge,
        selected_symbols=np.asarray(CONFIG["symbols"]),
    )
    symbols = np.asarray(CONFIG["symbols"])
    exact = workspace.select(symbols).values
    control = workspace.select(symbols, control=True).values
    if exact.shape != control.shape or exact.shape[0] < 2 or exact.shape[1] != 64:
        raise ValueError("candidate lacks matched complete64-symbol frame support")
    exact.setflags(write=False)
    control.setflags(write=False)
    return exact, control


def acquire_bank(acq, pm, templates, samples, rate, edge, acquisition_mode="coarse"):
    started = time.process_time()
    if acquisition_mode == "production":
        result = acq.acquire_symbolwise(
            samples, rate, acq.ReceiverFrequencyCalibration("RX", 0.0, "0" * 64),
            edge=edge, config=acq.SymbolwiseAcquisitionConfig(
                maximum_probe_samples=rate * CONFIG["window_ms"] // 1000,
                retained_candidate_count=CONFIG["candidate_count"],
            ),
        )
        if len(result.candidates) != CONFIG["candidate_count"]:
            raise ValueError(f"incomplete production candidate bank: {result.status}")
        bank = [{"candidate_id": i, "epoch_sample": c.refined_epoch_sample,
                 "seed_cfo_hz": c.absolute_cfo_hz, "coarse_score": c.coarse_score}
                for i, c in enumerate(result.candidates)]
        acquisition_cpu = time.process_time() - started
        started = time.process_time()
        pairs = [matrices(pm, samples, rate, edge, b["epoch_sample"], b["seed_cfo_hz"])
                 for b in bank]
        return bank, pairs, acquisition_cpu, time.process_time() - started
    grid = tuple(CONFIG["coarse_cfo_hz"])
    epoch_count = round(rate / templates.FRAME_RATE_HZ)
    template = np.asarray(templates.qin_edge_pilot_frame(rate, edge), np.complex128)
    maps = acq._folded_anchor_score_grid(
        samples, template, rate, grid, acq.DEFAULT_ANCHOR_SYMBOLS, epoch_count,
    )
    peaks = acq._retain_score_map_peaks(
        grid, maps, CONFIG["candidate_count"], CONFIG["epoch_separation_samples"],
        CONFIG["coarse_cfo_separation_hz"], epoch_count,
    )
    if len(peaks) != CONFIG["candidate_count"]:
        raise ValueError("incomplete common candidate bank; no silent skipped windows")
    bank = []
    for index, (score, epoch, cfo) in enumerate(peaks):
        epoch = acq._refine_epoch(maps[grid.index(cfo)], epoch, epoch_count)
        bank.append({"candidate_id": index, "epoch_sample": epoch, "seed_cfo_hz": cfo,
                     "coarse_score": score})
    acquisition_cpu = time.process_time() - started
    started = time.process_time()
    pairs = [matrices(pm, samples, rate, edge, b["epoch_sample"], b["seed_cfo_hz"])
             for b in bank]
    return bank, pairs, acquisition_cpu, time.process_time() - started


def score_common_bank(bank, pairs, scorer, **kwargs):
    if len(bank) != len(pairs) or len({b["candidate_id"] for b in bank}) != len(bank):
        raise ValueError("candidate/matrix bank mismatch")
    results, timing = {}, {}
    for candidate, (exact, control) in zip(bank, pairs, strict=True):
        started = time.process_time()
        values = scorer(exact, control, **kwargs)
        timing.setdefault("all_methods_cpu_s", 0.0)
        timing["all_methods_cpu_s"] += time.process_time() - started
        for method, result in values.items():
            entry = dict(candidate, **{k: float(v) for k, v in result.items()})
            entry["cfo_hz"] += candidate["seed_cfo_hz"]
            entry["control_cfo_hz"] += candidate["seed_cfo_hz"]
            entry["frame_count"] = len(exact)
            if not all(np.isfinite(v) for v in result.values()):
                raise ValueError("nonfinite score; no silent skipped methods")
            results.setdefault(method, []).append(entry)
    if any(len(rows) != len(bank) for rows in results.values()):
        raise ValueError("method omitted a common candidate")
    return {method: sorted(rows, key=lambda r: (-r["score"], r["candidate_id"]))
            for method, rows in results.items()}, timing


def summarize(rows: list[dict]) -> dict:
    result = {}
    methods = tuple(rows[0]["methods"])
    for split in SPLITS:
        subset = [r for r in rows if r["split"] == split]
        section = {}
        for method in methods:
            agreement, cfo_delta, rank_rho, consistency = [], [], [], []
            fixed_cfo_delta, winner_epoch_delta = [], []
            pairs: dict[tuple, list] = {}
            for row in subset:
                values = row["methods"][method]
                baseline = row["methods"]["current_glrt64_margin"]
                agreement.append(values[0]["candidate_id"] == baseline[0]["candidate_id"])
                cfo_delta.append(abs(values[0]["cfo_hz"] - baseline[0]["cfo_hz"]))
                same_candidates = {b["candidate_id"]: b for b in baseline}
                fixed_cfo_delta.extend(abs(v["cfo_hz"] -
                                           same_candidates[v["candidate_id"]]["cfo_hz"])
                                       for v in values)
                period = row["rate_hz"] / 750
                distance = abs(values[0]["epoch_sample"] - baseline[0]["epoch_sample"]) % period
                winner_epoch_delta.append(min(distance, period - distance))
                positions = {v["candidate_id"]: i for i, v in enumerate(baseline)}
                n = len(values)
                rank_rho.append(1 - 6 * sum((i - positions[v["candidate_id"]]) ** 2
                                           for i, v in enumerate(values)) / (n * (n * n - 1)))
                pairs.setdefault((row["case_id"], row["receiver"]), []).append(row)
            for key, pair in pairs.items():
                pair.sort(key=lambda r: r["window_start_ms"])
                if len(pair) != 2:
                    raise ValueError("nonoverlap consistency pair incomplete")
                a, b = [r["methods"][method][0] for r in pair]
                period = pair[0]["rate_hz"] / 750
                distance = abs(a["epoch_sample"] - b["epoch_sample"]) % period
                distance = min(distance, period - distance)
                delta = abs(a["cfo_hz"] - b["cfo_hz"])
                consistency.append({"case_id": key[0], "receiver": key[1],
                                    "cfo_delta_hz": delta, "epoch_delta_samples": distance,
                                    "joint_consistent": bool(delta <= 5000 and distance <=
                                                             pair[0]["rate_hz"] * 4.4e-6)})
            section[method] = {
                "windows": len(subset), "winner_agreement_with_current": float(np.mean(agreement)),
                "median_abs_cfo_change_from_current_hz": float(np.median(cfo_delta)),
                "max_fixed_candidate_abs_cfo_change_from_current_hz": max(fixed_cfo_delta),
                "median_winner_epoch_change_from_current_samples":
                    float(np.median(winner_epoch_delta)),
                "median_rank_spearman_with_current": float(np.median(rank_rho)),
                "nonoverlap_pairs": consistency,
                "joint_consistency_count": sum(c["joint_consistent"] for c in consistency),
                "median_nonoverlap_cfo_delta_hz": float(np.median(
                    [c["cfo_delta_hz"] for c in consistency])),
                "natural_score_quantiles": [float(v) for v in np.quantile(
                    [r["methods"][method][0]["score"] for r in subset], [0, .5, .9, 1])],
            }
        result[split] = section
    return result


def run(dataset: Path, output: Path, acquisition_mode: str = "coarse") -> None:
    frozen = json.loads((output / "selection.json").read_text())
    if (frozen["config"] != protocol(acquisition_mode) or
            digest(dataset / "cases.json") != frozen["dataset_manifest_sha256"]):
        raise ValueError("frozen protocol/input changed")
    selected, training = select_cases(json.loads((dataset / "cases.json").read_text()))
    if selected != frozen["selected"] or training != frozen["training"]:
        raise ValueError("frozen selection changed")
    acq, pm, templates = numerical_helpers()
    import methods
    paths = [Path(m.__file__) for m in (acq, pm, templates, methods)] + [Path(__file__)]
    if acq._native_acquisition is not None:
        paths.append(Path(acq._native_acquisition.__file__))
    sources = {str(p.relative_to(ROOT)): digest(p) for p in paths}
    provenance = {"sources": sources, "selection_sha256": digest(output / "selection.json"),
                  "python": sys.version, "numpy": np.__version__, "platform": platform.platform(),
                  "blas_thread_environment": {k: os.environ.get(k) for k in
                       ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")},
                  "acquisition_backend": acq._folded_anchor_score_grid_backend(),
                  "training_warning": (
                      "unlabeled development background may contain pilots; shared dev sessions "
                      "but disjoint visits; validation/holdout sessions excluded")}
    write_json(output / "provenance.json", provenance)
    whiteners, training_rows, training_cache = {}, {}, {}
    started = time.process_time()
    for rate in RATES:
        chunks = []
        for case in (c for c in training if c["rate_hz"] == rate):
            raw = load_iq(dataset, case)
            edge = templates.StarlinkEdge(case["edge"])
            exact_energy, _ = energies(pm, rate, edge)
            for rx in CONFIG["receivers"]:
                samples = raw[:rate // 50, rx, 0].astype(float) + 1j * raw[:rate // 50, rx, 1]
                exact, _ = matrices(pm, samples, rate, edge, 0, 0)
                chunks.append(exact / np.sqrt(exact_energy))
        train = np.concatenate(chunks)
        whiteners[rate] = methods.fit_whitener(train, shrinkage=CONFIG["shrinkage"])
        training_rows[str(rate)] = len(train)
        training_cache[f"r{rate}_normalized_rows"] = train
        training_cache[f"r{rate}_covariance"] = whiteners[rate].covariance
        training_cache[f"r{rate}_precision"] = whiteners[rate].precision
    training_cpu = time.process_time() - started
    np.savez_compressed(output / "training.npz", **training_cache)
    rows, cached = [], {}
    started_wall = time.monotonic()
    for case in selected:
        raw = load_iq(dataset, case)
        rate, edge = case["rate_hz"], templates.StarlinkEdge(case["edge"])
        exact_energy, control_energy = energies(pm, rate, edge)
        for rx in CONFIG["receivers"]:
            for ms in CONFIG["windows_start_ms"]:
                start, stop = rate * ms // 1000, rate * (ms + CONFIG["window_ms"]) // 1000
                samples = raw[start:stop, rx, 0].astype(float) + 1j * raw[start:stop, rx, 1]
                bank, pairs, acq_cpu, extraction_cpu = acquire_bank(
                    acq, pm, templates, samples, rate, edge, acquisition_mode,
                )
                scored, timing = score_common_bank(
                    bank, pairs, methods.score_bank, symbol_step_s=CONFIG["symbol_step_s"],
                    fft_size=CONFIG["fft_size"], whitener=whiteners[rate],
                    exact_template_energy=exact_energy, control_template_energy=control_energy,
                )
                row_index = len(rows)
                for b, (exact, control) in enumerate(pairs):
                    cached[f"r{row_index}_b{b}_exact"] = exact
                    cached[f"r{row_index}_b{b}_control"] = control
                rows.append({"case_id": case["case_id"], "split": case["split"],
                             "rate_hz": rate, "edge": case["edge"], "receiver": rx,
                             "window_start_ms": ms, "candidate_bank": bank, "methods": scored,
                             "acquisition_cpu_s": acq_cpu, "extraction_cpu_s": extraction_cpu,
                             **timing})
        print(f"completed {case['case_id']} ({len(rows)} windows)", flush=True)
    if {str(p.relative_to(ROOT)): digest(p) for p in paths} != sources:
        raise ValueError("numerical source changed during experiment")
    np.savez_compressed(output / "matrices.npz", **cached)
    write_json(output / "results.json", {"rows": rows, "summary": summarize(rows),
        "training_rows_per_rate": training_rows, "training_cpu_s": training_cpu,
        "wall_s": time.monotonic() - started_wall,
        "total_acquisition_cpu_s": sum(r["acquisition_cpu_s"] for r in rows),
        "total_extraction_cpu_s": sum(r["extraction_cpu_s"] for r in rows),
        "total_scoring_cpu_s": sum(r["all_methods_cpu_s"] for r in rows),
        "provenance_sha256": digest(output / "provenance.json"),
        "training_sha256": digest(output / "training.npz"),
        "matrices_sha256": digest(output / "matrices.npz")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("freeze", "run"))
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--acquisition", choices=("coarse", "production"), default="coarse")
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.dataset, args.output, args.acquisition)
    else:
        run(args.dataset, args.output, args.acquisition)
