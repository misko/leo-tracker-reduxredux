"""Prespecified segment comparisons on held-out windows and planted IQ pilots."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = ROOT / "reports/2026_10_07_glrt_detector_comparison"
sys.path[:0] = [str(PRIOR), str(HERE)]
import recorded as prior  # noqa: E402

CONFIG = {
    "selection": "fifth and sixth visits per real rate/split, both RX",
    "sizes": [64, 128, 256], "segment_lengths": [8, 16, 32, 64],
    "phase_kernel_lengths": [8, 16, 32], "fft_size": 512,
    "symbol_step_s": 4.4e-6, "windows_start_ms": [0, 40], "window_ms": 20,
    "candidate_count": 8, "shared_frame_support": "complete256-symbol frames for every N",
    "confirmation": "first-window selected timing and total CFO frozen; exact/control same CFO",
    "injections": {"splits": ["dev", "holdout"], "visits_per_rate": 1,
                   "receivers": [0, 1], "snr_db": [-30, -24, -18], "phase_sigma_rad": [0, .35],
                   "patterns": ["exact", "roll29"], "epoch_sample": 137, "cfo_hz": 57000,
                   "phase_process": ("iid Gaussian increments accumulated per frame; "
                                     "reset with uniform frame phase"),
                   "seed": 71007,
                   "power_reference": "integrated injected IQ / original window IQ power"},
    "threshold": "none; no calibration on sparse unlabeled background",
    "cfo_recovery_tolerance_hz": 5000, "epoch_recovery_tolerance_s": 4.4e-6,
}


def select(payload: dict) -> list[dict]:
    prior.select_cases(payload)  # Enforces scoring session disjointness and unknown real truth.
    selected = []
    for split in prior.SPLITS:
        for rate in prior.RATES:
            cases = sorted((c for c in payload["cases"] if c["origin"] == "real_ds5"
                            and c["split"] == split and c["rate_hz"] == rate),
                           key=lambda c: (c["visit_index"], c["case_id"]))
            if len(cases) != 8:
                raise ValueError("expected frozen eight-visit strata")
            selected.extend(cases[4:6])
    old_scored, old_training = prior.select_cases(payload)
    old_ids = {c["case_id"] for c in old_scored + old_training}
    if old_ids & {c["case_id"] for c in selected}:
        raise ValueError("followup cohort overlaps prior scored/training visits")
    return selected


def window(raw: np.ndarray, rate: int, rx: int, start_ms: int) -> np.ndarray:
    start, stop = rate * start_ms // 1000, rate * (start_ms + 20) // 1000
    if stop > len(raw) or rx not in (0, 1):
        raise ValueError("unsupported window geometry")
    return raw[start:stop, rx, 0].astype(float) + 1j * raw[start:stop, rx, 1]


def extract(pm, samples, rate, edge, epoch, cfo):
    symbols = np.arange(2, 258)
    workspace = pm._conditioned_correlation_workspace(
        samples, rate, epoch, cfo, edge=edge, selected_symbols=symbols,
    )
    exact = workspace.select(symbols).values
    control = workspace.select(symbols, control=True).values
    if exact.shape != control.shape or exact.shape[0] < 2 or exact.shape[1] != 256:
        raise ValueError("unsupported matched256-symbol candidate; no skipped cases")
    exact.setflags(write=False)
    control.setflags(write=False)
    return exact, control


def energy_vectors(pm, rate, edge):
    geometry = pm._conditioned_workspace_geometry(rate, edge)
    exact, control = np.zeros(300), np.zeros(300)
    for group in geometry.groups:
        exact[group.positions] = group.exact_energy
        control[group.positions] = group.control_energy
    if np.any(exact[:256] <= 0) or np.any(control[:256] <= 0):
        raise ValueError("nonpositive template energies")
    return exact[:256], control[:256]


def acquire(acq, samples, rate, edge):
    started = time.process_time()
    result = acq.acquire_symbolwise(
        samples, rate, acq.ReceiverFrequencyCalibration("RX", 0., "0" * 64), edge=edge,
        config=acq.SymbolwiseAcquisitionConfig(maximum_probe_samples=rate // 50,
                                             retained_candidate_count=8),
    )
    if len(result.candidates) != 8:
        raise ValueError(f"common production bank incomplete: {result.status}")
    bank = [{"candidate_id": i, "epoch_sample": c.refined_epoch_sample,
             "seed_cfo_hz": c.absolute_cfo_hz} for i, c in enumerate(result.candidates)]
    return bank, time.process_time() - started


def evaluate(bank, first, later, energy, scorer):
    """One common bank; later timing/CFO selected strictly from first observations."""
    if len(bank) != 8 or len(first) != 8 or len(later) != 8:
        raise ValueError("common candidate bank mismatch")
    output = {}
    started = time.process_time()
    for n in CONFIG["sizes"]:
        kwargs = dict(fft_size=512, symbol_step_s=4.4e-6,
                      exact_template_energy=energy[0][:n], control_template_energy=energy[1][:n])
        ranked = {}
        for candidate, (exact, control) in zip(bank, first, strict=True):
            if exact.shape != control.shape or exact.shape[1] != 256:
                raise ValueError("mismatched evidence")
            scores = scorer.score_bank(exact[:, :n], control[:, :n], **kwargs)
            for name, score in scores.items():
                fields = {k: float(v) for k, v in score.items()}
                if not all(np.isfinite(v) for v in fields.values()):
                    raise ValueError("nonfinite method output")
                ranked.setdefault(name, []).append(dict(candidate, **fields))
        if any(len(rows) != 8 for rows in ranked.values()):
            raise ValueError("missing method/candidate")
        result, memo = {}, {}
        for name, candidates in ranked.items():
            candidates.sort(key=lambda c: (-c["score"], c["candidate_id"]))
            winner = candidates[0]
            index, residual = winner["candidate_id"], winner["cfo_hz"]
            key = index, residual
            if key not in memo:
                exact, control = later[index]
                memo[key] = scorer.score_at_frequency(
                    exact[:, :n], control[:, :n], cfo_hz=residual, **kwargs,
                )
            confirmation = {k: float(v) for k, v in memo[key][name].items()}
            confirmation["exact_minus_control"] = (
                confirmation["exact_score"] - confirmation["control_score"])
            confirmation["total_cfo_hz"] = residual + winner["seed_cfo_hz"]
            result[name] = {"ranking": candidates, "winner": winner,
                            "confirmation_fixed_timing_frequency": confirmation,
                            "first_frame_count": len(first[index][0]),
                            "confirmation_frame_count": len(later[index][0])}
        output[str(n)] = result
    return output, time.process_time() - started


def injected_signal(templates, rate, edge, pattern, sigma, seed, start_ms=0):
    """Continuous nominal CFO, frame-reset phase walk; no new RF samples."""
    count = rate // 50
    offset = rate * start_ms // 1000
    epoch = CONFIG["injections"]["epoch_sample"]
    period = rate / templates.FRAME_RATE_HZ
    if pattern not in CONFIG["injections"]["patterns"]:
        raise ValueError("unrecognized injection pattern")
    roll = 0 if pattern == "exact" else 29
    template = np.asarray(templates.qin_edge_pilot_frame(rate, edge, symbol_roll=roll))
    result = np.zeros(count, complex)
    first_frame = int(np.floor((offset - epoch) / period))
    last_frame = int(np.ceil((offset + count - epoch) / period))
    local_symbols = np.minimum((np.arange(len(template)) / (rate * 4.4e-6)).astype(int), 301)
    for frame in range(first_frame, last_frame + 1):
        # A frame's random path is reproducible independently of requested window.
        rng = np.random.default_rng(np.random.SeedSequence([seed, frame + 1000]))
        phase = rng.uniform(-np.pi, np.pi) + np.cumsum(rng.normal(0, sigma, 302))
        source = template * np.exp(1j * phase[local_symbols])
        start = epoch + round(frame * period) - offset
        left, right = max(start, 0), min(start + len(source), count)
        if right > left:
            result[left:right] = source[left - start:right - start]
    indexes = np.arange(offset, offset + count)
    return result * np.exp(2j * np.pi * CONFIG["injections"]["cfo_hz"] * indexes / rate)


def add_injection(samples, signal, snr_db):
    background_power = float(np.mean(np.abs(samples) ** 2))
    pilot_power = float(np.mean(np.abs(signal) ** 2))
    if background_power <= 0 or pilot_power <= 0:
        raise ValueError("injection needs positive background and pilot power")
    scale = np.sqrt(background_power * 10 ** (snr_db / 10) / pilot_power)
    return samples + scale * signal, float(scale)


def recovery(winner, rate):
    period = rate / 750
    distance = abs(winner["epoch_sample"] - CONFIG["injections"]["epoch_sample"]) % period
    distance = min(distance, period - distance)
    frequency = winner["seed_cfo_hz"] + winner["cfo_hz"]
    error = abs(frequency - CONFIG["injections"]["cfo_hz"])
    return {"epoch_error_samples": distance, "cfo_error_hz": error,
            "timing_recovered": bool(distance <= rate * 4.4e-6),
            "cfo_recovered": bool(error <= 5000),
            "joint_recovered": bool(distance <= rate * 4.4e-6 and error <= 5000)}


def freeze(output):
    manifest = prior.DATASET / "cases.json"
    cases = select(json.loads(manifest.read_text()))
    config = dict(CONFIG, acquisition=prior.protocol("production")["production_acquisition_config"])
    value = {"config": config, "cases": cases, "manifest_sha256": prior.digest(manifest)}
    output.mkdir(parents=True, exist_ok=True)
    path = output / "selection.json"
    if path.exists() and json.loads(path.read_text()) != value:
        raise ValueError("frozen cohort/config changed")
    prior.write_json(path, value)


def summarize(raw, injected):
    result = {"raw": {}, "injections": {}}
    for split in prior.SPLITS:
        rows = [r for r in raw if r["split"] == split]
        section = {}
        for n in CONFIG["sizes"]:
            section[str(n)] = {}
            for name in rows[0]["scores"][str(n)]:
                items = [r["scores"][str(n)][name] for r in rows]
                margin = [i["confirmation_fixed_timing_frequency"]["exact_minus_control"]
                          for i in items]
                section[str(n)][name] = {
                    "count": len(items),
                    "confirmation_positive_margin_count": sum(m > 0 for m in margin),
                    "confirmation_margin_quantiles": np.quantile(margin, [0, .5, .9, 1]).tolist(),
                    "first_score_quantiles": np.quantile([i["winner"]["score"] for i in items],
                                                         [0, .5, .9, 1]).tolist(),
                }
        result["raw"][split] = section
    for split in ("dev", "holdout"):
        section = {}
        for sigma in CONFIG["injections"]["phase_sigma_rad"]:
            for snr in CONFIG["injections"]["snr_db"]:
                for pattern in CONFIG["injections"]["patterns"]:
                    rows = [r for r in injected if r["split"] == split and r["sigma"] == sigma
                            and r["snr_db"] == snr and r["pattern"] == pattern]
                    group = {}
                    for n in CONFIG["sizes"]:
                        group[str(n)] = {}
                        for name in rows[0]["scores"][str(n)]:
                            items = [r["scores"][str(n)][name] for r in rows]
                            group[str(n)][name] = {
                                "count": len(items),
                                "joint_recovered": sum(
                                    i["recovery"]["joint_recovered"] for i in items),
                                "confirmed_positive_margin": sum(
                                    i["confirmation_fixed_timing_frequency"]
                                    ["exact_minus_control"] > 0
                                    for i in items),
                                "median_confirmation_margin": float(np.median([
                                    i["confirmation_fixed_timing_frequency"]["exact_minus_control"]
                                    for i in items])),
                            }
                    section[f"sigma{sigma}_snr{snr}_{pattern}"] = group
        result["injections"][split] = section
    return result


def run(output):
    frozen = json.loads((output / "selection.json").read_text())
    expected_config = dict(CONFIG, acquisition=
                           prior.protocol("production")["production_acquisition_config"])
    if frozen["config"] != expected_config:
        raise ValueError("frozen configuration changed")
    if prior.digest(prior.DATASET / "cases.json") != frozen["manifest_sha256"]:
        raise ValueError("dataset manifest changed")
    if select(json.loads((prior.DATASET / "cases.json").read_text())) != frozen["cases"]:
        raise ValueError("cohort changed")
    acq, pm, templates = prior.numerical_helpers()
    sys.path.insert(0, str(HERE))
    import segment_methods as methods
    paths = [Path(m.__file__) for m in (prior, acq, pm, templates, methods)] + [Path(__file__)]
    if acq._native_acquisition is not None:
        paths.append(Path(acq._native_acquisition.__file__))
    source_hashes = {str(p.relative_to(ROOT)): prior.digest(p) for p in paths}
    prior.write_json(output / "provenance.json", {
        "sources": source_hashes, "selection_sha256": prior.digest(output / "selection.json"),
        "numpy": np.__version__, "python": sys.version,
        "thread_environment": {k: os.environ.get(k) for k in
                               ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")},
    })
    raw_rows, injection_rows, cache = [], [], {}
    total_acq = total_extract = total_score = 0.
    wall = time.monotonic()
    for case in frozen["cases"]:
        raw = prior.load_iq(prior.DATASET, case)
        rate, edge = case["rate_hz"], templates.StarlinkEdge(case["edge"])
        energy = energy_vectors(pm, rate, edge)
        for rx in (0, 1):
            first, later = [window(raw, rate, rx, ms) for ms in (0, 40)]
            bank, cpu = acquire(acq, first, rate, edge)
            total_acq += cpu
            started = time.process_time()
            pairs = [[extract(pm, samples, rate, edge, c["epoch_sample"], c["seed_cfo_hz"])
                      for c in bank] for samples in (first, later)]
            total_extract += time.process_time() - started
            scores, cpu = evaluate(bank, pairs[0], pairs[1], energy, methods)
            total_score += cpu
            index = len(raw_rows)
            for wi, observations in enumerate(pairs):
                for bi, (exact, control) in enumerate(observations):
                    cache[f"r{index}_w{wi}_b{bi}_exact"] = exact
                    cache[f"r{index}_w{wi}_b{bi}_control"] = control
            raw_rows.append({"case_id": case["case_id"], "split": case["split"],
                             "rate_hz": rate, "edge": case["edge"], "receiver": rx,
                             "candidate_bank": bank, "scores": scores})
        print(f"raw complete {case['case_id']}", flush=True)
    backgrounds = [c for c in frozen["cases"] if c["split"] in ("dev", "holdout")]
    backgrounds = [c for c in backgrounds if c == min(
        [b for b in backgrounds if b["split"] == c["split"] and b["rate_hz"] == c["rate_hz"]],
        key=lambda b: b["visit_index"])]
    for case_index, case in enumerate(backgrounds):
        raw = prior.load_iq(prior.DATASET, case)
        rate, edge = case["rate_hz"], templates.StarlinkEdge(case["edge"])
        energy = energy_vectors(pm, rate, edge)
        for rx in (0, 1):
            original = [window(raw, rate, rx, ms) for ms in (0, 40)]
            for sigma in CONFIG["injections"]["phase_sigma_rad"]:
                for snr in CONFIG["injections"]["snr_db"]:
                    for pattern in CONFIG["injections"]["patterns"]:
                        seed = CONFIG["injections"]["seed"] + case_index * 2 + rx
                        signals = [injected_signal(templates, rate, edge, pattern, sigma, seed, ms)
                                   for ms in (0, 40)]
                        first, scale = add_injection(original[0], signals[0], snr)
                        # Keep the same injected amplitude in held-out observations.
                        later = original[1] + scale * signals[1]
                        bank, cpu = acquire(acq, first, rate, edge)
                        total_acq += cpu
                        started = time.process_time()
                        pairs = [[extract(pm, samples, rate, edge,
                                          c["epoch_sample"], c["seed_cfo_hz"])
                                  for c in bank] for samples in (first, later)]
                        total_extract += time.process_time() - started
                        scores, cpu = evaluate(bank, pairs[0], pairs[1], energy, methods)
                        total_score += cpu
                        for values in scores.values():
                            for item in values.values():
                                item["recovery"] = recovery(item["winner"], rate)
                                item["retained_estimate_oracle_recovery"] = any(
                                    recovery(c, rate)["joint_recovered"] for c in item["ranking"])
                        survival = [recovery(dict(c, cfo_hz=0.), rate) for c in bank]
                        grid = np.fft.fftfreq(512, d=4.4e-6)
                        reachable = any(s["timing_recovered"] and
                            np.min(np.abs(c["seed_cfo_hz"] + grid - 57000)) <= 5000
                            for c, s in zip(bank, survival, strict=True))
                        injection_rows.append({"case_id": case["case_id"], "split": case["split"],
                            "rate_hz": rate, "edge": case["edge"], "receiver": rx, "seed": seed,
                            "sigma": sigma, "snr_db": snr, "pattern": pattern, "scale": scale,
                            "candidate_bank": bank, "scores": scores,
                            "planted_timing_in_bank": any(s["timing_recovered"] for s in survival),
                            "planted_timing_cfo_grid_reachable": bool(reachable),
                            "planted_seed_timing_cfo_in_bank": any(
                                s["joint_recovered"] for s in survival)})
        print(f"injections complete {case['case_id']}", flush=True)
    if {str(p.relative_to(ROOT)): prior.digest(p) for p in paths} != source_hashes:
        raise ValueError("source changed; rejecting all experiment results")
    np.savez_compressed(output / "matrices.npz", **cache)
    prior.write_json(output / "results.json", {
        "raw": raw_rows, "injected": injection_rows, "summary": summarize(raw_rows, injection_rows),
        "total_acquisition_cpu_s": total_acq, "total_extraction_cpu_s": total_extract,
        "total_scoring_cpu_s": total_score, "wall_s": time.monotonic() - wall,
        "matrices_sha256": prior.digest(output / "matrices.npz"),
        "provenance_sha256": prior.digest(output / "provenance.json"),
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("freeze", "run"))
    parser.add_argument("--output", type=Path, default=HERE / "recorded")
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.output)
    else:
        run(args.output)
