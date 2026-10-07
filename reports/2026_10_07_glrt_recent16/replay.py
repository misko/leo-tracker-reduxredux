"""Bounded full-cohort replay using read-only ports and frozen candidate scoring."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

for _variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_variable] = "1"

import numpy as np  # noqa: E402
from evaluator import evaluate_bank  # noqa: E402
from source_adapter import (  # noqa: E402
    ArchivedSource,
    ci16_window,
    correlations64,
    normalize_bank,
    template_energies,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SELECTION = HERE / "selection.json"
FROZEN_SCORER = HERE.parent / "2026_10_07_glrt_segment_followup/segment_methods.py"
EXPECTED_SCORER_SHA256 = "06c341391596c60dc885a5fafdcd4c169614dfe96a3492fff77c2f84fd2a7b33"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def expected_probes(raw_count, rate, receivers=(0, 1)):
    dwell_ms, remainder = divmod(raw_count * 1000, rate)
    if remainder or dwell_ms not in (120, 240, 360):
        raise ValueError("visit duration is outside the archived variable-dwell contract")
    return {
        (rx, index): start
        for rx in receivers
        for index, start in enumerate(range(0, dwell_ms - 20 + 1, 120))
    }


def validate_probe_inventory(probes, raw_count, rate):
    expected = expected_probes(raw_count, rate)
    observed = [(int(probe["receiver_id"]), int(probe["probe_index"])) for probe in probes]
    if len(observed) != len(set(observed)) or set(observed) != set(expected):
        raise ValueError("archived GLRT probe inventory does not cover the saved visit")
    return expected


def runtime():
    from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore

    from leo.analysis.starlink import templates

    numerical_path = ROOT / "src/leo/analysis/starlink/pilot_methods.py"
    spec = importlib.util.spec_from_file_location("recent16_pilot_math", numerical_path)
    pm = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = pm
    spec.loader.exec_module(pm)
    iq = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    analysis = AdaptiveHopAnalysisStore(Path("/srv/bulk/leo"), read_only=True)
    source = ArchivedSource(iq, analysis, bind_actual_visit_analysis)
    paths = [
        Path(__file__),
        HERE / "source_adapter.py",
        HERE / "evaluator.py",
        FROZEN_SCORER,
        numerical_path,
        Path(templates.__file__),
    ]
    for kind in (AdaptiveHopIqStore, AdaptiveHopAnalysisStore):
        paths.append(Path(sys.modules[kind.__module__].__file__))
    paths.append(Path(sys.modules[bind_actual_visit_analysis.__module__].__file__))
    hashes = {str(path): digest(path) for path in paths}
    if digest(FROZEN_SCORER) != EXPECTED_SCORER_SHA256:
        raise ValueError("previously selected scorer source changed")
    return source, pm, templates, hashes


def error_record(scan, visit_index, error, probe=None):
    rx = None if probe is None else int(probe["receiver_id"])
    index = None if probe is None else int(probe["probe_index"])
    return {
        "scan_id": scan["session_id"],
        "session_id": scan["session_id"],
        "label": scan["label"],
        "visit_index": visit_index,
        "receiver": rx,
        "probe_index": index,
        "case_id": f"{scan['session_id']}:v{visit_index:06d}:rx{rx}:p{index}",
        "status": "execution_error",
        "error_type": type(error).__name__,
        "error": str(error),
    }


def run_scan(task):
    scan, output_name, deadline_seconds = task
    output = Path(output_name)
    directory = output / scan["label"]
    directory.mkdir(exist_ok=False)
    started_wall, started_cpu = time.monotonic(), time.process_time()
    source, pm, templates, hashes = runtime()
    totals = {
        "visits_expected": scan["total_visits"],
        "visits_processed": 0,
        "probes_expected": 0,
        "probes_written": 0,
        "probes_complete": 0,
        "probe_errors": 0,
        "empty_banks": 0,
        "saved_candidates": 0,
        "available_candidates": 0,
        "unavailable_candidates": 0,
        "raw_bytes_read": 0,
        "metadata_cpu_s": 0.0,
        "raw_read_cpu_s": 0.0,
        "extraction_cpu_s": 0.0,
        "scoring_cpu_s": 0.0,
        "serialization_cpu_s": 0.0,
    }
    errors, baseline_max, baseline_counts = [], {}, {}
    rate = scan["sample_rate_hz"]
    archive = directory / "results.jsonl.gz"
    finished = False
    try:
        with gzip.open(archive, "wt", compresslevel=1) as stream:
            admission_started = time.process_time()
            with source.scan(scan) as (session, metrics, job, reader):
                totals["metadata_cpu_s"] += time.process_time() - admission_started
                indices = [int(visit.visit_index) for visit in metrics.visits]
                if len(indices) != len(set(indices)) or len(indices) != scan["total_visits"]:
                    raise ValueError("sealed metrics visit accounting differs")
                audit_visits = {indices[0], indices[len(indices) // 2], indices[-1]}
                seen_visits = set()
                products = iter(job.published_visits())
                while True:
                    begin = time.process_time()
                    try:
                        typed_product = next(products)
                    except StopIteration:
                        break
                    product = typed_product.model_dump(mode="json")
                    visit_index = int(typed_product.visit_index)
                    totals["metadata_cpu_s"] += time.process_time() - begin
                    if visit_index not in indices or visit_index in seen_visits:
                        raise ValueError("published visit differs from sealed inventory")
                    seen_visits.add(visit_index)
                    if time.monotonic() - started_wall > deadline_seconds:
                        raise TimeoutError("per-scan replay exceeded frozen runtime budget")
                    begin = time.process_time()
                    visit, raw = reader.read_visit_ci16(visit_index)
                    totals["raw_read_cpu_s"] += time.process_time() - begin
                    totals["raw_bytes_read"] += raw.nbytes
                    if (
                        product["input_manifest_sha256"] != session.manifest_sha256
                        or int(product["valid_start_counter"]) != visit.event.valid_start_counter
                    ):
                        raise ValueError("GLRT/raw visit identity or counters differ")
                    expected = validate_probe_inventory(product["probes"], len(raw), rate)
                    totals["probes_expected"] += len(expected)
                    edge = visit.event.target.edge
                    energy = template_energies(pm, templates, rate, edge)
                    raw_hash = hashlib.sha256(memoryview(raw).cast("B")).hexdigest()
                    for probe in product["probes"]:
                        rx, index = int(probe["receiver_id"]), int(probe["probe_index"])
                        first_ms = expected[rx, index]
                        try:
                            bank, coverage = normalize_bank(probe)
                            totals["saved_candidates"] += coverage["saved_candidate_count"]
                            totals["available_candidates"] += len(bank)
                            totals["unavailable_candidates"] += len(
                                coverage["unavailable_candidates"]
                            )
                            case = {
                                "scan_id": scan["session_id"],
                                "session_id": scan["session_id"],
                                "label": scan["label"],
                                "visit_index": visit_index,
                                "receiver": rx,
                                "probe_index": index,
                                    "case_id": (
                                        f"{scan['session_id']}:v{visit_index:06d}:rx{rx}:p{index}"
                                    ),
                                "sample_rate_hz": rate,
                                "edge": str(edge),
                                "first_window_start_ms": first_ms,
                                "later_window_start_ms": first_ms + 40,
                                "raw_visit_sha256": raw_hash,
                                "valid_start_counter": visit.event.valid_start_counter,
                                "candidate_bank": bank,
                                **coverage,
                            }
                            if not bank:
                                case["status"] = "no_available_candidates"
                                totals["empty_banks"] += 1
                            else:
                                begin = time.process_time()
                                pairs = []
                                for ms in (first_ms, first_ms + 40):
                                    samples = ci16_window(raw, rate, rx, ms)
                                    pairs.append(
                                        [
                                            correlations64(
                                                pm,
                                                templates,
                                                samples,
                                                rate,
                                                edge,
                                                candidate["epoch_sample"],
                                                candidate["seed_cfo_hz"],
                                            )
                                            for candidate in bank
                                        ]
                                    )
                                totals["extraction_cpu_s"] += time.process_time() - begin
                                evaluation = evaluate_bank(
                                    bank,
                                    pairs[0],
                                    pairs[1],
                                    exact_template_energy=energy[0],
                                    control_template_energy=energy[1],
                                )
                                totals["scoring_cpu_s"] += evaluation["cost"]["total_process_cpu_s"]
                                case["evaluation"] = evaluation
                                case["status"] = "complete"
                                totals["probes_complete"] += 1
                                comparison = evaluation["baseline_comparison"]
                                for key, value in comparison["max_absolute_errors"].items():
                                    baseline_max[key] = max(baseline_max.get(key, 0.0), value)
                                for key, value in comparison["compared_counts"].items():
                                    baseline_counts[key] = baseline_counts.get(key, 0) + value
                                if visit_index in audit_visits and index == 0:
                                    arrays = {
                                        "exact_template_energy": energy[0],
                                        "control_template_energy": energy[1],
                                    }
                                    for wi, values in enumerate(pairs):
                                        for ci, pair in enumerate(values):
                                            arrays[f"w{wi}_c{ci}_exact"] = pair[0]
                                            arrays[f"w{wi}_c{ci}_control"] = pair[1]
                                    prefix = f"audit-v{visit_index:06d}-rx{rx}"
                                    np.savez_compressed(directory / f"{prefix}.npz", **arrays)
                                    write_json(directory / f"{prefix}.json", case)
                        except Exception as error:
                            case = error_record(scan, visit_index, error, probe)
                            errors.append(case)
                            totals["probe_errors"] += 1
                        begin = time.process_time()
                        stream.write(
                            json.dumps(case, separators=(",", ":"), allow_nan=False) + "\n"
                        )
                        totals["serialization_cpu_s"] += time.process_time() - begin
                        totals["probes_written"] += 1
                    totals["visits_processed"] += 1
                    if totals["visits_processed"] % 32 == 0:
                        write_json(
                            directory / "progress.json",
                            dict(
                                totals, wall_s=time.monotonic() - started_wall, label=scan["label"]
                            ),
                        )
                if seen_visits != set(indices):
                    raise ValueError("published stream omitted sealed visits")
                finished = True
    except Exception as error:
        errors.append(error_record(scan, totals["visits_processed"], error))
    finally:
        source.iq.close()
        source.analysis.close()
    for name, expected_hash in hashes.items():
        if digest(name) != expected_hash:
            errors.append({"error": "source_changed_during_run", "path": name})
            finished = False
    result = {
        "scan": scan,
        "status": "complete" if finished and not errors else "incomplete",
        "coverage": totals,
        "errors": errors,
        "baseline_max_errors": baseline_max,
        "baseline_compared_counts": baseline_counts,
        "source_sha256": hashes,
        "selection_sha256": digest(SELECTION),
        "archive_sha256": digest(archive),
        "wall_s": time.monotonic() - started_wall,
        "process_cpu_s": time.process_time() - started_cpu,
    }
    write_json(directory / "receipt.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--per-scan-seconds", type=int, default=1200)
    args = parser.parse_args()
    selected = json.loads(SELECTION.read_text())
    if len(selected["scans"]) != 16 or not 1 <= args.workers <= 4:
        raise ValueError("requires the fixed sixteen-scan cohort and at most four workers")
    args.output.mkdir(exist_ok=False)
    config = {
        "selection_sha256": digest(SELECTION),
        "replay_sha256": digest(__file__),
        "workers": args.workers,
        "per_scan_seconds": args.per_scan_seconds,
        "coverage": "every archived GLRT probe in every sealed visit, all16scans",
        "candidate_scope": "every archived available candidate; unavailable ranks retained",
        "first_window_ms": [0, 20],
        "confirmation_offset_ms": 40,
        "aperture_symbols": list(range(2, 66)),
        "fft_size": 512,
        "audit_visits": "first, middle, last sealed visit per scan, both RX, probe0",
    }
    write_json(args.output / "run_config.json", config)
    begun = time.monotonic()
    tasks = [(scan, str(args.output), args.per_scan_seconds) for scan in selected["scans"]]
    receipts = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_scan, task): task[0] for task in tasks}
        for future in as_completed(futures):
            result = future.result()
            receipts.append(result)
            print(
                json.dumps(
                    {
                        "label": result["scan"]["label"],
                        "status": result["status"],
                        "coverage": result["coverage"],
                        "wall_s": result["wall_s"],
                    }
                ),
                flush=True,
            )
    write_json(
        args.output / "index.json",
        {
            "receipts": receipts,
            "wall_s": time.monotonic() - begun,
            "complete_scans": sum(row["status"] == "complete" for row in receipts),
        },
    )
    if any(row["status"] != "complete" for row in receipts):
        raise SystemExit("incomplete replay; inspect all preserved receipts")


if __name__ == "__main__":
    main()
