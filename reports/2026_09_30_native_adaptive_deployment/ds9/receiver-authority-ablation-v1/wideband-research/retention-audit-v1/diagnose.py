#!/usr/bin/env python3
"""Reproduce the fixed-eight DS9 retention result with source frequency authority."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np


VISITS = (126, 191, 193, 283, 301, 307, 346, 418)
RATE = 7_500_000
PROBE_SAMPLES = RATE // 50
LNB_LO_HZ = 9_750_000_000
RESIDUALS = tuple(float(value) for value in range(-800_000, 800_001, 80_000))
FALLBACK_ANCHOR_SYMBOLS = tuple(range(2, 302, 14))
FLOAT_FIELDS = (
    ("fractional_offset", "fractional_offset"),
    ("tracking_cfo_hz", "tracking_cfo_hz"),
    ("exact_score", "exact_score"),
    ("control_score", "control_score"),
    ("margin", "margin"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_call(path: Path) -> dict:
    for line in path.read_text().splitlines():
        item = json.loads(line)
        if "result" in item:
            return item["result"]
    raise ValueError(f"no result in {path}")


def candidate(candidate) -> dict:
    return {
        "rank": candidate.candidate_rank,
        "integer_epoch": candidate.epoch_sample,
        "acquired_cfo_hz": candidate.acquired_cfo_hz,
        "integer_tracking_cfo_hz": candidate.tracking_cfo_hz,
        "integer_exact_score": candidate.exact_score,
        "integer_control_score": candidate.control_score,
        "integer_margin": candidate.margin,
        "fractional_status": candidate.fractional_epoch_status,
        "fractional_offset": candidate.fractional_epoch_offset_samples,
        "tracking_cfo_hz": candidate.fractional_tracking_cfo_hz,
        "exact_score": candidate.fractional_exact_score,
        "control_score": candidate.fractional_control_score,
        "margin": candidate.fractional_margin,
    }


def native_candidates(call: dict) -> list[dict]:
    row = next(item for item in call["rows"] if item["receiver_id"] == 0)
    result = []
    for rank, item in enumerate(row["candidates"]):
        fractional = item["fractional_epoch"]
        result.append(
            {
                "rank": rank,
                "coarse_epoch": item["coarse_epoch"],
                "coarse_residual_cfo_hz": item["coarse_cfo_hz"],
                "coarse_score": item["coarse_score"],
                "integer_epoch": item["epoch"],
                "acquired_cfo_hz": item["acquired_cfo_hz"],
                "integer_tracking_cfo_hz": item["tracking_cfo_hz"],
                "integer_exact_score": item["exact_score"],
                "integer_control_score": item["control_score"],
                "integer_margin": item["margin"],
                "fractional_status": fractional["status"],
                "fractional_offset": fractional.get("offset_samples"),
                "tracking_cfo_hz": fractional.get("tracking_cfo_hz"),
                "exact_score": fractional.get("exact_score"),
                "control_score": fractional.get("control_score"),
                "margin": fractional.get("margin"),
            }
        )
    return result


def compare_persisted(persisted: list[dict], actual: list[dict]) -> dict:
    by_rank = {item["rank"]: item for item in actual}
    comparisons = []
    all_exact = True
    maximum = {field: 0.0 for field, _ in FLOAT_FIELDS}
    for item in persisted:
        expected = item["candidate"]
        observed = by_rank[expected["rank"]]
        row = {
            "rank": expected["rank"],
            "integer_epoch_equal": expected["integer_epoch"] == observed["integer_epoch"],
            "projection_gate_equal": expected["complete"]
            == (
                observed["fractional_status"] == "complete"
                and observed["margin"] >= 0.025
            ),
            "deltas": {},
        }
        for expected_name, actual_name in FLOAT_FIELDS:
            delta = abs(float(expected[expected_name]) - float(observed[actual_name]))
            row["deltas"][expected_name] = delta
            maximum[expected_name] = max(maximum[expected_name], delta)
            all_exact &= delta == 0.0
        all_exact &= row["integer_epoch_equal"] and row["projection_gate_equal"]
        comparisons.append(row)
    return {
        "rows": len(comparisons),
        "all_fields_bit_exact": all_exact,
        "maximum_absolute_delta": maximum,
        "comparisons": comparisons,
    }


def coarse_inventory(acquisition, values: np.ndarray, center_hz: float) -> list[dict]:
    template = np.asarray(
        acquisition.qin_edge_pilot_frame(RATE, acquisition.StarlinkEdge.LOWER),
        dtype=np.complex128,
    )
    scores = acquisition._folded_anchor_score_grid(
        values,
        template,
        RATE,
        tuple(center_hz + residual for residual in RESIDUALS),
        acquisition.DEFAULT_ANCHOR_SYMBOLS,
        round(RATE / acquisition.FRAME_RATE_HZ),
    )
    peaks = []
    for residual, row in zip(RESIDUALS, scores, strict=True):
        peaks.extend(
            (float(row[epoch]), epoch, residual)
            for epoch in acquisition._local_peak_indexes(row)
        )
    peaks.sort(key=lambda item: (item[0], -abs(item[2]), -item[1]), reverse=True)
    retained = acquisition._retain_separated(peaks, 8, 5, 10_000.0, 10_000)
    return [
        {
            "retention_index": index,
            "score": score,
            "epoch": epoch,
            "residual_cfo_hz": residual,
            "absolute_cfo_hz": center_hz + residual,
        }
        for index, (score, epoch, residual) in enumerate(retained)
    ]


def compare_zero_center_coarse(server: list[dict], native: list[dict]) -> dict:
    """Compare coarse retention as a multiset; refinement may reorder final ranks."""

    server_rows = sorted(
        (
            item["epoch"],
            item["absolute_cfo_hz"],
            item["score"],
        )
        for item in server
    )
    native_rows = sorted(
        (
            item["coarse_epoch"],
            item["coarse_residual_cfo_hz"],
            item["coarse_score"],
        )
        for item in native
    )
    rows = []
    coordinates_equal = len(server_rows) == len(native_rows)
    maximum_score_delta = 0.0
    for server_row, native_row in zip(server_rows, native_rows, strict=False):
        row = {
            "server": server_row,
            "native": native_row,
            "epoch_equal": server_row[0] == native_row[0],
            "cfo_equal": server_row[1] == native_row[1],
            "score_delta": abs(server_row[2] - native_row[2]),
        }
        coordinates_equal &= row["epoch_equal"] and row["cfo_equal"]
        maximum_score_delta = max(maximum_score_delta, row["score_delta"])
        rows.append(row)
    return {
        "coordinate_multiset_equal": coordinates_equal,
        "maximum_score_absolute_delta": maximum_score_delta,
        "rows": rows,
    }


def compare_full_candidates(server: list[dict], native: list[dict]) -> dict:
    """Compare all retained candidates, including below-gate and unbracketed rows."""

    numeric_fields = (
        "acquired_cfo_hz",
        "integer_tracking_cfo_hz",
        "integer_exact_score",
        "integer_control_score",
        "integer_margin",
        "fractional_offset",
        "tracking_cfo_hz",
        "exact_score",
        "control_score",
        "margin",
    )
    maximum = {field: 0.0 for field in numeric_fields}
    exact_structure = len(server) == len(native)
    rows = []
    for expected, observed in zip(server, native, strict=False):
        row = {
            "rank": expected["rank"],
            "rank_equal": expected["rank"] == observed["rank"],
            "integer_epoch_equal": expected["integer_epoch"] == observed["integer_epoch"],
            "fractional_status_equal": expected["fractional_status"]
            == observed["fractional_status"],
            "deltas": {},
        }
        exact_structure &= (
            row["rank_equal"]
            and row["integer_epoch_equal"]
            and row["fractional_status_equal"]
        )
        for field in numeric_fields:
            left = expected[field]
            right = observed[field]
            if left is None or right is None:
                equal = left is None and right is None
                row["deltas"][field] = None if equal else "null-mismatch"
                exact_structure &= equal
                continue
            delta = abs(float(left) - float(right))
            row["deltas"][field] = delta
            maximum[field] = max(maximum[field], delta)
        rows.append(row)
    within_tolerance = exact_structure and all(
        delta <= (1e-6 if "cfo_hz" in field else 1e-10)
        for field, delta in maximum.items()
    )
    return {
        "rows": len(rows),
        "structure_equal": exact_structure,
        "within_frozen_tolerance": within_tolerance,
        "maximum_absolute_delta": maximum,
        "comparisons": rows,
    }


def main() -> None:
    here = Path(__file__).resolve().parent
    root = here.parents[5]
    reference = Path("/var/tmp/leo-arm-realtime-publication")
    sys.path.insert(0, str(reference / "src"))
    from leo.analysis.starlink import acquisition
    from leo.analysis.starlink.pilot_search_geometry import compile_pilot_search_geometry
    from leo.scanner import detector

    authority_path = here.parents[1] / "missing-rx0-replay/raw-authority.json"
    projection_path = (
        root
        / "reports/2026_09_30_native_adaptive_deployment/tracking/projection-inputs.jsonl"
    )
    zero_native_dir = here.parent / "fixed8"
    authority = {item["visit"]: item for item in json.loads(authority_path.read_text())}
    persisted = {visit: [] for visit in VISITS}
    for line in projection_path.read_text().splitlines():
        item = json.loads(line)
        source = item.get("source") or {}
        if (
            source.get("visit") in persisted
            and source.get("receiver") == 0
            and source.get("probe_index") == 0
        ):
            persisted[source["visit"]].append(item)

    config = SimpleNamespace(
        sample_rate_hz=RATE,
        maximum_acquisition_candidates=8,
        glrt64_margin_gate=0.025,
        probe_stride_ms=120,
    )
    acquisition_config = acquisition.SymbolwiseAcquisitionConfig(
        residual_cfo_min_hz=-800_000,
        residual_cfo_max_hz=800_000,
        retained_candidate_count=8,
        candidate_epoch_separation_samples=5,
        candidate_cfo_separation_hz=10_000,
        maximum_probe_samples=PROBE_SAMPLES,
    )
    visits = []
    for visit in VISITS:
        source = authority[visit]
        actual_if_hz = source["actual_rf_hz"] - LNB_LO_HZ
        geometry = compile_pilot_search_geometry(
            receiver_id=0,
            starlink_channel=source["channel"],
            edge=source["edge"],
            tuned_center_frequency_hz=actual_if_hz,
            sample_rate_hz=RATE,
            rf_bandwidth_hz=RATE,
            residual_cfo_min_hz=-800_000,
            residual_cfo_max_hz=800_000,
            lnb_lo_hz=LNB_LO_HZ,
        )
        raw_path = Path(source["raw"])
        raw = np.fromfile(raw_path, dtype="<i2").reshape(-1, 4)[:PROBE_SAMPLES]
        values = raw[:, 0].astype(np.float64) + 1j * raw[:, 1].astype(np.float64)
        server = detector._evaluate_probe(
            values,
            config,
            geometry.frequency_reference,
            edge=source["edge"],
            acquisition_config=acquisition_config,
            receiver_id=0,
            probe_index=0,
        )
        server_candidates = [candidate(item) for item in server.candidates]
        corrected_native = native_candidates(load_call(here / f"visit-{visit:04d}.jsonl"))
        zero_native = native_candidates(load_call(zero_native_dir / f"wrapper-{visit}.jsonl"))
        authoritative_coarse = coarse_inventory(
            acquisition, values, geometry.frequency_reference.center_hz
        )
        zero_coarse = coarse_inventory(acquisition, values, 0.0)
        visits.append(
            {
                "visit": visit,
                "channel": source["channel"],
                "raw": str(raw_path),
                "raw_sha256": sha256(raw_path),
                "geometry": {
                    "tuned_if_hz": actual_if_hz,
                    "pilot_if_center_hz": geometry.pilot_if_center_frequency_hz,
                    "receiver_center_hz": geometry.frequency_reference.center_hz,
                    "residual_min_hz": -800_000,
                    "residual_max_hz": 800_000,
                },
                "persisted_rows": persisted[visit],
                "current_server_authoritative_coarse_inventory": authoritative_coarse,
                "current_server_zero_center_coarse_inventory": zero_coarse,
                "current_server_authoritative_candidates": server_candidates,
                "native_corrected_center_candidates": corrected_native,
                "native_zero_center_candidates": zero_native,
                "persisted_vs_current_server": compare_persisted(
                    persisted[visit], server_candidates
                ),
                "persisted_vs_corrected_native": compare_persisted(
                    persisted[visit], corrected_native
                ),
                "current_server_vs_corrected_native_all_candidates": compare_full_candidates(
                    server_candidates, corrected_native
                ),
                "current_server_vs_native_zero_center_coarse": compare_zero_center_coarse(
                    zero_coarse, zero_native
                ),
            }
        )

    native_module = Path(acquisition._native_acquisition.__file__)
    result = {
        "schema": "org.leo.ds9-receiver-center-retention-audit/v1",
        "scope": {
            "visits": list(VISITS),
            "receiver": 0,
            "probe_index": 0,
            "sample_rate_hz": RATE,
            "probe_samples": PROBE_SAMPLES,
            "hardware_or_rf_used": False,
            "production_source_changed": False,
        },
        "finding": {
            "persisted_receiver_center_hz": -312_500.0,
            "isolated_wideband_schedule_receiver_center_hz": 0.0,
            "mechanism": (
                "coarse residual bins are converted to absolute CFO with the receiver center "
                "before local-peak retention; the 312.5 kHz grid translation changes which "
                "eight coarse paths survive, and no post-refinement canonicalization removes "
                "paths that later converge"
            ),
        },
        "authorized_standard": {
            "persisted_product_schema_version": 9,
            "persisted_configuration_schema_version": 6,
            "analyzer_id": "adaptive-hop-variable-dwell-fractional-glrt64-cfo-v1",
            "binding_sha256": (
                "sha256:4ff246ba978647e28e725a2c55066b8f79aa685b3310df6f4ca7e4006d4bd702"
            ),
            "input_manifest_sha256": (
                "sha256:5b8755586b9a84444ea3caf1bcb5cb0f6c6d80b7c9e3087666331608883de2bd"
            ),
            "metrics_manifest_contract_sha256": (
                "sha256:b381b859fb9f566a26c3e08b3215619a19c5ac53af80632f713ce96077d1ca59"
            ),
            "configuration": {
                "sample_rate_hz": RATE,
                "allowed_valid_visit_ms": [120, 240, 360],
                "probe_ms": 20,
                "probe_stride_ms": 120,
                "glrt64_margin_gate": 0.025,
                "maximum_acquisition_candidates": 8,
                "receiver_ids": [0, 1],
                "timing_refinement": (
                    "circular-five-cell-log-parabola-plus-lanczos16-v1"
                ),
                "decision_score": "fractional-epoch-conditioned-glrt64-v1",
            },
            "historical_executable_source_hash_bound_in_public_binding": False,
            "interpretation": (
                "the persisted schema-v9 product and binding remain the parity target; "
                "the current maintained implementation independently reproduces its eight "
                "retained candidate sets and numbers, but the public binding does not "
                "cryptographically identify the historical Python source or native DSO"
            ),
        },
        "algorithm": {
            "initial_anchor_symbols": list(acquisition.DEFAULT_ANCHOR_SYMBOLS),
            "initial_anchor_count": len(acquisition.DEFAULT_ANCHOR_SYMBOLS),
            "fallback_anchor_symbols": list(FALLBACK_ANCHOR_SYMBOLS),
            "fallback_anchor_count": len(FALLBACK_ANCHOR_SYMBOLS),
            "rx0_fallback_triggered_on_eight_visits": False,
            "retained_candidate_count": 8,
            "candidate_epoch_separation_samples": 5,
            "candidate_cfo_separation_hz": 10_000,
            "residual_cfo_step_hz": 80_000,
        },
        "provenance": {
            "reference_git_head": subprocess.check_output(
                ["git", "-C", str(reference), "rev-parse", "HEAD"], text=True
            ).strip(),
            "python": sys.version,
            "numpy": np.__version__,
            "coarse_backend": acquisition._folded_anchor_score_grid_backend(),
            "native_acquisition_dso": str(native_module),
            "native_acquisition_sha256": sha256(native_module),
            "source_sha256": {
                str(path.relative_to(reference)): sha256(path)
                for path in (
                    reference / "src/leo/analysis/starlink/acquisition.py",
                    reference / "src/leo/analysis/starlink/pilot_search_geometry.py",
                    reference / "src/leo/scanner/detector.py",
                    reference / "src/leo/scanner/adaptive_hop_analysis.py",
                    reference / "src/leo/contracts/starlink_frequency.py",
                    reference / "src/leo/analysis/starlink/templates.py",
                )
            },
            "persisted_server_analysis": str(
                root
                / "reports/2026_09_30_native_adaptive_deployment/ds9/location-selection"
                / "server_analysis.json"
            ),
            "persisted_binding_sha256": (
                "be19c3b21b3a3214add20b4987aa71f1e22eedb49d0f5f879546fdeb5ea2e385"
            ),
            "persisted_metrics_manifest_sha256": (
                "37d43809775cd072466de2bc5f2dd100e26018b9314b910a256d37021812e501"
            ),
            "zero_center_native_comparison": str(here.parent / "comparison.json"),
            "native_replay": str(here.parent / "artifacts/host/leo-native-adaptive-replay"),
            "native_replay_sha256": sha256(
                here.parent / "artifacts/host/leo-native-adaptive-replay"
            ),
            "inputs": {
                "raw_authority_sha256": sha256(authority_path),
                "projection_inputs_sha256": sha256(projection_path),
                "corrected_schedule_sha256": {
                    f"visit-{visit:04d}.tsv": sha256(
                        here / f"schedules/visit-{visit:04d}.tsv"
                    )
                    for visit in VISITS
                },
                "zero_center_schedule_sha256": {
                    f"wrapper-{visit:04d}.tsv": sha256(
                        Path("/var/tmp/leo-rx0-missing8-replay.wi1oVv/schedules")
                        / f"wrapper-{visit:04d}.tsv"
                    )
                    for visit in VISITS
                },
            },
        },
        "summary": {
            "persisted_rows": sum(len(persisted[visit]) for visit in VISITS),
            "persisted_gate_rows_equal": sum(
                comparison["projection_gate_equal"]
                for visit in visits
                for comparison in visit["persisted_vs_current_server"]["comparisons"]
            ),
            "persisted_passing_rows": sum(
                item["candidate"]["complete"]
                for visit in VISITS
                for item in persisted[visit]
            ),
            "corrected_native_passing_candidates": sum(
                item["margin"] is not None and item["margin"] >= 0.025
                for visit in visits
                for item in visit["native_corrected_center_candidates"]
            ),
            "current_server_authoritative_all_rows_bit_exact": all(
                item["persisted_vs_current_server"]["all_fields_bit_exact"] for item in visits
            ),
            "corrected_native_rows_within_tolerance": all(
                all(
                    delta <= (1e-6 if field == "tracking_cfo_hz" else 1e-10)
                    for field, delta in item["persisted_vs_corrected_native"][
                        "maximum_absolute_delta"
                    ].items()
                )
                for item in visits
            ),
            "zero_center_server_native_coarse_coordinates_equal": all(
                item["current_server_vs_native_zero_center_coarse"]
                ["coordinate_multiset_equal"]
                for item in visits
            ),
            "current_server_corrected_native_all_candidates_within_tolerance": all(
                item["current_server_vs_corrected_native_all_candidates"]
                ["within_frozen_tolerance"]
                for item in visits
            ),
        },
        "visits": visits,
    }
    (here / "diagnostic.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
