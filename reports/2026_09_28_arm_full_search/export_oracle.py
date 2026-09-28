"""Export four bounded frozen-reference probes as a native-port oracle."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = ROOT / "src"
FROZEN_ACQUISITION = (
    ROOT / "reports/2026_09_27_server_scan_speed/acquisition_peak/original/acquisition.py"
)
FROZEN_PILOT = ROOT / "reports/2026_09_27_server_scan_speed/pilot_methods_baseline.py"
SEALED_BASELINE = ROOT / "reports/2026_09_28_ds7_large_arm/baseline-01/rows.jsonl"
ZERO_CALIBRATION_SHA256 = "0" * 64
MARGIN_GATE = 0.025
FLOAT_TOLERANCE = 1e-10


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load frozen source {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_frozen() -> tuple[ModuleType, ModuleType]:
    """Load the preserved source files, never the optimized implementation."""

    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    return (
        _load_module(FROZEN_ACQUISITION, "_arm_oracle_original_acquisition"),
        _load_module(FROZEN_PILOT, "_arm_oracle_original_pilot"),
    )


def select_cases(rows: list[dict[str, Any]], *, all_rates: bool = False) -> list[dict[str, Any]]:
    """Choose first saved input per requested native rate and edge."""

    selected: list[dict[str, Any]] = []
    rates = (2_500_000, 5_000_000, 7_500_000, 10_000_000) if all_rates else (2_500_000,)
    for rate in rates:
        for edge in ("lower", "upper"):
            found = next(
                (row for row in rows if row["rate_hz"] == rate and row["target"]["edge"] == edge),
                None,
            )
            if found is not None:
                selected.append(found)
    return selected


def _write_array(path: Path, values: np.ndarray, dtype: str) -> dict[str, Any]:
    array = np.ascontiguousarray(values, dtype=np.dtype(dtype))
    array.tofile(path)
    return {
        "file": path.name,
        "sha256": sha256(path),
        "dtype": np.dtype(dtype).str,
        "shape": list(array.shape),
        "order": "C",
    }


def _candidate(candidate: object) -> dict[str, Any]:
    return {
        name: _json_number(getattr(candidate, name))
        for name in (
            "rank",
            "coarse_epoch_sample",
            "coarse_residual_cfo_hz",
            "refined_epoch_sample",
            "residual_cfo_hz",
            "absolute_cfo_hz",
            "coarse_score",
            "acquire_score",
            "verify_score",
            "conditioned_exact_score",
            "conditioned_control_score",
            "verify_minus_control_margin",
            "frame_support",
        )
    }


def _final(score: object) -> dict[str, Any]:
    return {
        "exact_score": _json_number(score.exact_score),
        "control_score": _json_number(score.control_score),
        "margin": _json_number(score.margin),
        "residual_cfo_hz": _json_number(score.residual_cfo_hz),
        "tracking_cfo_hz": _json_number(score.tracking_cfo_hz),
        "passed_margin_gate": bool(score.margin >= MARGIN_GATE),
    }


def _json_number(value: object) -> int | float:
    if isinstance(value, (int, np.integer)):
        return int(value)
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("oracle values must be finite")
    return result


def _baseline_probe(context: dict[str, Any], receiver_id: int) -> list[dict[str, Any]]:
    """Return the sealed original repeat-0 probe zero for one receiver."""

    matches: list[dict[str, Any]] = []
    for line in SEALED_BASELINE.read_text().splitlines():
        row = json.loads(line)
        if (
            row.get("method") == "original"
            and row.get("repeat") == 0
            and row.get("status") == "ok"
            and row["context"]["session_id"] == context["session_id"]
            and row["context"]["visit_index"] == context["visit_index"]
        ):
            matches.extend(
                probe["candidates"]
                for probe in row["result"]["probes"]
                if probe["probe_index"] == 0 and probe["receiver_id"] == receiver_id
            )
    if len(matches) != 1:
        raise ValueError("sealed baseline does not contain exactly one matching original probe")
    return matches[0]


def assert_matches_baseline(
    candidates: list[dict[str, Any]], final: list[dict[str, Any]], baseline: list[dict[str, Any]]
) -> None:
    """Bind the exported original scope to the independently sealed full run."""

    if len(candidates) != len(final) or len(candidates) != len(baseline):
        raise ValueError("sealed baseline candidate count differs")
    for candidate, score, expected in zip(candidates, final, baseline, strict=True):
        if candidate["rank"] != expected["candidate_rank"]:
            raise ValueError("sealed baseline candidate rank differs")
        if candidate["refined_epoch_sample"] != expected["epoch_sample"]:
            raise ValueError("sealed baseline epoch differs")
        for actual, reference, label in (
            (candidate["absolute_cfo_hz"], expected["acquired_cfo_hz"], "acquired CFO"),
            (score["residual_cfo_hz"], expected["residual_cfo_hz"], "final residual CFO"),
            (score["tracking_cfo_hz"], expected["tracking_cfo_hz"], "tracking CFO"),
            (score["exact_score"], expected["exact_score"], "exact score"),
            (score["control_score"], expected["control_score"], "control score"),
            (score["margin"], expected["margin"], "margin"),
        ):
            if not math.isclose(actual, reference, rel_tol=0.0, abs_tol=FLOAT_TOLERANCE):
                raise ValueError(f"sealed baseline {label} differs")


def export(inputs: Path, output: Path, *, all_rates: bool = False) -> dict[str, Any]:
    """Write a small deterministic oracle.  The only evaluated probes are 0/11."""

    receipt_path = inputs / "inputs.json"
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("schema") != "ds7-large-arm-inputs/v1" or not receipt.get("complete"):
        raise ValueError("input receipt is not the complete large-ARM input set")
    selected = select_cases(receipt["rows"], all_rates=all_rates)
    if not selected:
        raise ValueError("no requested native-rate lower or upper saved input exists")
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    acquisition, pilot = load_frozen()
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame

    document: dict[str, Any] = {
        "schema": "arm-full-search-oracle/v1",
        "selection": (
            "first inputs.json-order saved window per requested native rate and edge; "
            "metadata only; probe 0 and both receivers only"
        ),
        "all_rates": all_rates,
        "input_manifest": {"file": str(receipt_path), "sha256": sha256(receipt_path)},
        "frozen_sources": {
            "acquisition": {"file": str(FROZEN_ACQUISITION), "sha256": sha256(FROZEN_ACQUISITION)},
            "pilot": {"file": str(FROZEN_PILOT), "sha256": sha256(FROZEN_PILOT)},
        },
        "coarse_search": {
            "residual_cfo_min_hz": -400000.0,
            "residual_cfo_max_hz": 400000.0,
            "coarse_cfo_step_hz": 80000.0,
            "anchor_symbols": list(acquisition.DEFAULT_ANCHOR_SYMBOLS),
            "grid_layout": "CFO-major float64 rows; columns are epoch samples 0..round(rate/750)-1",
        },
        "final_glrt": {
            "pilot_symbol_range_inclusive": [2, 65],
            "glrt_size": 512,
            "margin_gate": MARGIN_GATE,
        },
        "cases": [],
    }
    try:
        for context in selected:
            source = inputs / context["file"]
            if sha256(source) != context["sha256"]:
                raise ValueError("saved IQ hash differs from input receipt")
            raw = np.load(source, allow_pickle=False)
            if list(raw.shape) != context["shape"] or str(raw.dtype) != context["dtype"]:
                raise ValueError("saved IQ geometry differs from input receipt")
            rate = int(context["rate_hz"])
            edge = context["target"]["edge"]
            probe_samples = rate * 20 // 1000
            exact = np.asarray(qin_edge_pilot_frame(rate, edge), dtype="<c16")
            control = np.asarray(
                qin_edge_pilot_frame(rate, edge, symbol_roll=CONTROL_SYMBOL_ROLL), dtype="<c16"
            )
            prefix = f"{edge}-{context['session_id']}-v{context['visit_index']}"
            template_files = {
                "exact": _write_array(output / f"{prefix}-exact.c128", exact, "<c16"),
                "control": _write_array(output / f"{prefix}-control.c128", control, "<c16"),
            }
            config = acquisition.SymbolwiseAcquisitionConfig(
                maximum_probe_samples=probe_samples,
                retained_candidate_count=8,
                candidate_epoch_separation_samples=5,
                candidate_cfo_separation_hz=10000.0,
            )
            residuals = acquisition._bounded_grid(-400000.0, 400000.0, 80000.0)
            case: dict[str, Any] = {
                "context": context,
                "probe": {
                    "index": 0,
                    "start_sample": 0,
                    "sample_count": probe_samples,
                    "start_ms": 0,
                },
                "templates": template_files,
                "receivers": [],
            }
            for receiver_id in (0, 1):
                probe = np.ascontiguousarray(raw[:probe_samples, receiver_id, 0], dtype=np.float64)
                probe = probe + 1j * np.asarray(
                    raw[:probe_samples, receiver_id, 1], dtype=np.float64
                )
                probe = np.asarray(probe, dtype="<c16")
                raw_file = _write_array(
                    output / f"{prefix}-rx{receiver_id}-probe0.c128", probe, "<c16"
                )
                calibration = acquisition.ReceiverFrequencyCalibration(
                    receiver_id=str(receiver_id),
                    center_hz=0.0,
                    calibration_sha256=ZERO_CALIBRATION_SHA256,
                )
                coarse = acquisition._folded_anchor_score_grid(
                    probe,
                    exact,
                    rate,
                    tuple(float(value) for value in residuals),
                    config.anchor_symbols,
                    round(rate / 750.0),
                )
                coarse_array = np.asarray(coarse, dtype="<f8")
                coarse_file = _write_array(
                    output / f"{prefix}-rx{receiver_id}-probe0-coarse.f64", coarse_array, "<f8"
                )
                acquired = acquisition.acquire_symbolwise(
                    probe, rate, calibration, edge=edge, config=config
                )
                candidates = [_candidate(candidate) for candidate in acquired.candidates]
                final = [
                    _final(
                        pilot.conditioned_glrt64_score(
                            probe,
                            rate,
                            epoch_sample=candidate.refined_epoch_sample,
                            acquired_cfo_hz=candidate.absolute_cfo_hz,
                            edge=edge,
                        )
                    )
                    for candidate in acquired.candidates
                ]
                assert_matches_baseline(candidates, final, _baseline_probe(context, receiver_id))
                case["receivers"].append(
                    {
                        "receiver_id": receiver_id,
                        "raw_probe": raw_file,
                        "coarse_grid": {**coarse_file, "residual_cfo_hz": list(residuals)},
                        "acquisition_status": str(acquired.status),
                        "retained_candidates": candidates,
                        "final_glrt512": final,
                        "sealed_baseline_match": True,
                    }
                )
            document["cases"].append(case)
        (output / "oracle.json").write_text(json.dumps(document, indent=2, allow_nan=False) + "\n")
        return document
    except Exception:
        shutil.rmtree(output)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=Path("/var/tmp/leo-ds7-large-arm-20260928"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--all-rates",
        action="store_true",
        help="include first lower/upper input at 2.5, 5, 7.5, and 10 MS/s",
    )
    args = parser.parse_args()
    document = export(args.inputs, args.output, all_rates=args.all_rates)
    print(json.dumps({"output": str(args.output), "cases": len(document["cases"])}))


if __name__ == "__main__":
    main()
