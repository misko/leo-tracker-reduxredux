"""Frozen exact-coordinate diagnostic for the TG11 v1078 extra decision."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import statistics
import sys
import time

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
ROOT = HERE.parents[2]
TG11 = REPORT / "tg11"
sys.path[:0] = [str(ROOT / "src"), str(TG11), str(HERE)]

import numpy as np
import leo
import leo.analysis.starlink.pilot_methods as pilot_methods
import leo.analysis.starlink.templates as templates

if Path(leo.__file__).resolve() != ROOT / "src/leo/__init__.py":
    raise RuntimeError("diagnostic must use the current repository leo package")
if Path(templates.__file__).resolve() != ROOT / "src/leo/analysis/starlink/templates.py":
    raise RuntimeError("diagnostic must use current repository templates")

from native_engine import NativeTG11
import tg11_dataset as dataset

THREAD_ENV = (
    "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS",
)


def digest(path: str | Path) -> str:
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def array_digest(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).view(np.uint8)).hexdigest()


def timed(function):
    cpu, wall = time.process_time_ns(), time.perf_counter_ns()
    result = function()
    return result, {
        "process_cpu_ms": (time.process_time_ns() - cpu) / 1e6,
        "wall_ms": (time.perf_counter_ns() - wall) / 1e6,
    }


def source_files() -> dict[str, str]:
    paths = {
        HERE / "config.json", HERE / "run_diagnostic.py", HERE / "test_diagnostic.py",
        TG11 / "phase1_cost_results.json", TG11 / "source_lock_phase1.json",
        TG11 / "native_engine.py", TG11 / "decision.py", TG11 / "tg11_dataset.py",
        TG11 / "libtg11.so", TG11 / "libtg11.so.build.json",
        Path(pilot_methods.__file__), Path(templates.__file__),
        ROOT / "src/leo/analysis/starlink/acquisition.py",
    }
    paths |= set(dataset.SOURCE_HASHES)
    native_receipt = json.loads((TG11 / "libtg11.so.build.json").read_text())
    if digest(TG11 / "libtg11.so") != native_receipt["binary_sha256"]:
        raise ValueError("TG11 native binary changed")
    for name, expected in native_receipt["sources_sha256"].items():
        if digest(name) != expected:
            raise ValueError(f"TG11 native dependency changed: {name}")
        paths.add(Path(name))
    return {str(path.resolve()): digest(path) for path in sorted(paths)}


def config_and_receipt() -> tuple[dict, dict]:
    config = json.loads((HERE / "config.json").read_text())
    receipt_path = TG11 / "phase1_cost_results.json"
    if digest(receipt_path) != config["phase1_result_sha256"]:
        raise ValueError("authoritative phase-one receipt changed")
    receipt = json.loads(receipt_path.read_text())
    return config, receipt


def verify_lock(lock: dict) -> None:
    for name, expected in lock["files"].items():
        if digest(name) != expected:
            raise ValueError(f"frozen diagnostic source changed: {name}")
    if lock["membership_digest"] != dataset.membership_digest():
        raise ValueError("TG11 membership changed")


def integer_cells(epoch: float) -> tuple[int, ...]:
    return tuple(sorted({math.floor(epoch), round(epoch), math.ceil(epoch)}))


def complex_probe(raw: np.ndarray, rate: int, receiver: int, probe: int) -> np.ndarray:
    start = probe * rate // 100
    selected = raw[start:start + rate // 50, receiver]
    values = np.empty(len(selected), dtype=np.complex64)
    values.real = selected[:, 0]
    values.imag = selected[:, 1]
    values.setflags(write=False)
    return values


def python_score(probe: np.ndarray, rate: int, edge: str, epoch: int, cfo: float) -> dict:
    score = pilot_methods.conditioned_glrt64_score(
        probe, rate, epoch_sample=epoch, acquired_cfo_hz=cfo, edge=edge
    )
    return asdict(score)


def python_support(probe: np.ndarray, rate: int, edge: str, epoch: int, cfo: float) -> int:
    workspace = pilot_methods._conditioned_correlation_workspace(
        probe, rate, epoch, cfo, selected_symbols=np.arange(2, 66),
        edge=templates.StarlinkEdge(edge),
    )
    return int(workspace.select(np.arange(2, 66)).values.shape[0])


def nearest_application_candidates(receipt_row: dict, receiver: int, epoch: float,
                                   cfo: float, rate: int) -> dict:
    period = rate / 750.0
    rows = []
    for probe in receipt_row["application_output"]["probes"]:
        if probe["receiver_id"] != receiver:
            continue
        for candidate in probe["candidates"]:
            dwell_epoch = probe["probe_start_ms"] * rate // 1000 + candidate["epoch_sample"]
            timing = abs((epoch - dwell_epoch + period / 2) % period - period / 2)
            cfo_error = abs(cfo - candidate["tracking_cfo_hz"])
            rows.append((timing / (rate * 2e-6) + cfo_error / 8000,
                         timing, cfo_error, probe["probe_index"], candidate))
    _, timing, cfo_error, probe, candidate = min(rows, key=lambda item: item[0])
    return {"probe_index": probe, "timing_error_samples": timing,
            "timing_error_us": timing / rate * 1e6, "cfo_error_hz": cfo_error,
            "candidate": candidate,
            "within_identity_gate": timing <= rate * 2e-6 and cfo_error <= 8000}


def matching_blind(observations, coordinate: dict, rate: int):
    period = rate / 750.0
    same_probe = [item for item in observations
                  if item.probe_index == coordinate["probe_index"]]
    if not same_probe:
        raise ValueError("blind rerun exposed no candidate in receipt probe")
    return min(same_probe, key=lambda item: (
        abs((item.local_epoch_sample - coordinate["local_epoch_sample"] + period / 2)
            % period - period / 2) / (rate * 2e-6)
        + abs(item.acquired_cfo_hz - coordinate["scoring_cfo_hz"]) / 8000
    ))


def score_coordinate(engine, raw, case, receipt_row, receiver: int, coordinate: dict,
                     blind_observations) -> dict:
    probe_index = coordinate["probe_index"]
    epoch = coordinate["local_epoch_sample"]
    cfo = coordinate["scoring_cfo_hz"]
    probe = complex_probe(raw, case.rate, receiver, probe_index)
    cells = integer_cells(epoch)
    python_cells = []
    native_cells = []
    for cell in cells:
        score = python_score(probe, case.rate, case.edge, cell, cfo)
        score["epoch_sample"] = cell
        score["support_frames"] = python_support(
            probe, case.rate, case.edge, cell, cfo
        )
        python_cells.append(score)
        native = engine.guided(
            raw, receiver=receiver, probe_index=probe_index,
            predicted_local_epoch_sample=float(cell), scoring_cfo_hz=cfo,
            expected_physical_cfo_hz=cfo,
        )
        if native is None:
            raise ValueError("native integer guided score failed")
        native_cells.append(asdict(native))
    exact = engine.guided(
        raw, receiver=receiver, probe_index=probe_index,
        predicted_local_epoch_sample=epoch, scoring_cfo_hz=cfo,
        expected_physical_cfo_hz=cfo,
    )
    if exact is None:
        raise ValueError("native exact guided score failed")
    blind = matching_blind(blind_observations, coordinate, case.rate)
    nearest_cell = round(epoch)
    # Warmups are explicit and excluded.
    engine.guided(raw, receiver=receiver, probe_index=probe_index,
                  predicted_local_epoch_sample=epoch, scoring_cfo_hz=cfo,
                  expected_physical_cfo_hz=cfo)
    python_score(probe, case.rate, case.edge, nearest_cell, cfo)
    timing = {"native_exact_guided": [], "python_nearest_integer": []}
    for _ in range(3):
        _, measured = timed(lambda: engine.guided(
            raw, receiver=receiver, probe_index=probe_index,
            predicted_local_epoch_sample=epoch, scoring_cfo_hz=cfo,
            expected_physical_cfo_hz=cfo,
        ))
        timing["native_exact_guided"].append(measured)
        _, measured = timed(lambda: python_score(
            probe, case.rate, case.edge, nearest_cell, cfo
        ))
        timing["python_nearest_integer"].append(measured)
    timing_summary = {
        name: {field: statistics.median(row[field] for row in values)
               for field in ("process_cpu_ms", "wall_ms")}
        for name, values in timing.items()
    }
    selected_python = next(item for item in python_cells
                           if item["epoch_sample"] == nearest_cell)
    selected_native = next(item for item in native_cells
                           if round(item["local_epoch_sample"]) == nearest_cell)
    return {
        "receipt_coordinate": coordinate,
        "probe_ci16_sha256": array_digest(
            raw[probe_index * case.rate // 100:
                probe_index * case.rate // 100 + case.rate // 50, receiver]
        ),
        "probe_complex64_sha256": array_digest(probe),
        "blind_rerun": asdict(blind),
        "blind_receipt_margin_delta": blind.margin - coordinate["receipt_margin"],
        "native_exact_fractional": asdict(exact),
        "native_integer_cells": native_cells,
        "python_integer_cells": python_cells,
        "nearest_integer": nearest_cell,
        "same_integer_comparison": {
            "native_margin": selected_native["margin"],
            "python_margin": selected_python["margin"],
            "margin_delta_native_minus_python": (
                selected_native["margin"] - selected_python["margin"]
            ),
            "native_exact_score": selected_native["exact_score"],
            "python_exact_score": selected_python["exact_score"],
            "native_control_score": selected_native["control_score"],
            "python_control_score": selected_python["control_score"],
        },
        "nearest_application_candidate": nearest_application_candidates(
            receipt_row, receiver,
            probe_index * case.rate // 100 + epoch, cfo, case.rate
        ),
        "timing_repetitions": timing,
        "timing_medians": timing_summary,
    }


def interpret(case_rows: list[dict], gate: float) -> dict:
    extra = next(item for item in case_rows
                 if item["role"] == "unadjudicated_additional_tg11_pair")
    anchor = next(item for item in case_rows
                  if item["role"] == "retained_known_positive_anchor")
    def pair_status(case):
        python = [max(cell["margin"] for cell in row["python_integer_cells"])
                  for row in case["coordinates"]]
        native_integer = [max(cell["margin"] for cell in row["native_integer_cells"])
                          for row in case["coordinates"]]
        native_blind = [row["blind_rerun"]["margin"] for row in case["coordinates"]]
        python_tracking = [
            max(row["python_integer_cells"], key=lambda cell: cell["margin"])["tracking_cfo_hz"]
            for row in case["coordinates"]
        ]
        return {
            "python_best_integer_margins": python,
            "python_pair_positive": all(value >= gate for value in python)
                and abs(python_tracking[1] - python_tracking[0]) <= 8000,
            "native_best_integer_margins": native_integer,
            "native_integer_pair_positive": all(value >= gate for value in native_integer),
            "native_blind_margins": native_blind,
            "native_blind_pair_positive": all(value >= gate for value in native_blind),
            "application_search_has_matching_identity": all(
                row["nearest_application_candidate"]["within_identity_gate"]
                for row in case["coordinates"]
            ),
        }
    extra_status = pair_status(extra)
    anchor_status = pair_status(anchor)
    if extra_status["python_pair_positive"] and not extra_status[
        "application_search_has_matching_identity"
    ]:
        conclusion = "python_conditioned_score_passes_at_tg_coordinates_but_search_did_not_retain_them"
    elif extra_status["native_integer_pair_positive"] and not extra_status["python_pair_positive"]:
        conclusion = "native_and_python_conditioned_statistics_disagree_at_same_integer_coordinates"
    elif extra_status["native_blind_pair_positive"] and not extra_status["native_integer_pair_positive"]:
        conclusion = "native_blind_fractional_or_conditioned_path_differs_from_integer_guided_score"
    else:
        conclusion = "mixed_or_unresolved_coordinate_effect"
    return {"extra": extra_status, "anchor": anchor_status, "conclusion": conclusion}


def main() -> None:
    lock_path = HERE / "source_lock.json"
    result_path = HERE / "results.json"
    if sys.argv[1:] == ["--freeze"]:
        if lock_path.exists():
            raise ValueError("preserve diagnostic lock")
        config, _ = config_and_receipt()
        payload = {"stage": "frozen_before_tg11_extra_diagnostic",
                   "files": source_files(), "config": config,
                   "membership_digest": dataset.membership_digest()}
        lock_path.write_text(json.dumps(payload, indent=2) + "\n")
        return
    if sys.argv[1:]:
        raise ValueError("unexpected arguments")
    if result_path.exists():
        raise ValueError("preserve diagnostic result")
    environment = {name: os.environ.get(name) for name in THREAD_ENV}
    if any(value != "1" for value in environment.values()):
        raise ValueError("all numerical threads must equal one")
    lock = json.loads(lock_path.read_text())
    verify_lock(lock)
    config, receipt = config_and_receipt()
    cases = {case.id: case for case in dataset.timing_cases()}
    receipt_rows = {row["case_id"]: row for row in receipt["rows"]}
    affinity = os.sched_getaffinity(0)
    if 0 not in affinity:
        raise ValueError("P-core 0 unavailable")
    rows, status, error = [], "complete", None
    started = time.perf_counter()
    previous = signal.signal(signal.SIGALRM,
        lambda *_: (_ for _ in ()).throw(TimeoutError("60 second diagnostic bound")))
    signal.alarm(60)
    try:
        os.sched_setaffinity(0, {0})
        for item in config["cases"]:
            case = cases[item["case_id"]]
            raw = dataset.load_iq(case)
            before = hashlib.sha256(raw).hexdigest()
            with NativeTG11(case.rate, case.edge, library=TG11 / "libtg11.so") as engine:
                screen = engine.screen(raw, receiver=item["receiver"])
                blind = engine.blind(raw, receiver=item["receiver"], screen=screen)
                coordinates = [score_coordinate(
                    engine, raw, case, receipt_rows[case.id], item["receiver"], coordinate, blind
                ) for coordinate in item["coordinates"]]
            if hashlib.sha256(raw).hexdigest() != before:
                raise ValueError("diagnostic input mutated")
            rows.append({"role": item["role"], "case_id": case.id,
                         "receiver": item["receiver"], "raw_sha256": case.raw_sha256,
                         "input_immutable": True, "coordinates": coordinates})
            print(json.dumps({"case": case.id, "coordinates": len(coordinates)}), flush=True)
    except Exception as caught:
        status = "timed_out_partial" if isinstance(caught, TimeoutError) else "failed"
        error = f"{type(caught).__name__}: {caught}"
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        os.sched_setaffinity(0, affinity)
    stable = all(digest(name) == expected for name, expected in lock["files"].items())
    interpretation = interpret(rows, config["decision_margin_gate"]) if len(rows) == 2 else None
    exact_template = templates.qin_edge_pilot_frame(2_500_000, "upper")
    control_template = templates.qin_edge_pilot_frame(
        2_500_000, "upper", symbol_roll=templates.CONTROL_SYMBOL_ROLL
    )
    payload = {"schema": "org.leo.research.tg11-extra-diagnostic/v1",
               "status": status, "error": error, "source_lock": lock,
               "source_lock_stable": stable, "thread_environment": environment,
               "affinity_cpu": 0, "affinity_restored": sorted(affinity),
               "template_source": str(Path(templates.__file__).resolve()),
               "template_sha256": {"exact_complex64": array_digest(exact_template),
                                   "control_complex64": array_digest(control_template)},
               "statistic_contract": {
                   "native_profile": "decision-band FP32 FFTW with GLRT_SYMBOL_DIVERSITY=1",
                   "native_final_symbols": "frames alternate symbols 2..65 and 152..215; late support falls back to 2..65",
                   "python_final_symbols": "conditioned_glrt64_score uses symbols 2..65 on every frame",
                   "native_blind_preprocessing": "tone nuisance fit may be applied before acquisition/final score",
                   "native_guided_preprocessing": "raw strided samples; no new nuisance fit",
                   "timing": "native exact fractional and integer cells; Python integer cells only",
                   "comparison_semantics": "different detector statistics; scores are diagnostic and not an equivalence oracle"
               },
               "rows": rows, "interpretation": interpretation,
               "holdout_opened": False, "elapsed_seconds": time.perf_counter() - started}
    result_path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": status, "interpretation": interpretation}), flush=True)


if __name__ == "__main__":
    main()
