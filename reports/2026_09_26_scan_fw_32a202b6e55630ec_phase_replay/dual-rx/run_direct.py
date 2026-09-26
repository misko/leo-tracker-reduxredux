"""Run method 24 over the sealed cohort from digest-verified source chunks."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
REPORT = HERE.parent
CACHE_INDEX = Path(
    "/srv/bulk/leo-dev/scan-32a202-phase-replay-cache/selected-visits/cache-index.json"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "phase_replay_dual_rx_analysis", HERE / "analysis.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


A = _load_module()


def _load_common():
    spec = importlib.util.spec_from_file_location("phase_replay_common", REPORT / "common.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


C = _load_common()


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _score_model(phasors, counters, train_mask, held_mask, row, degree):
    cfo, rate, intercept = A.fit_phase_frequency_rate(
        phasors[train_mask],
        counters[train_mask],
        integer_origin=row["valid_start_counter"],
        sample_rate_hz=10_000_000,
        degree=degree,
    )
    error = A.prediction_error(
        phasors[held_mask],
        counters[held_mask],
        integer_origin=row["valid_start_counter"],
        sample_rate_hz=10_000_000,
        cfo_hz=cfo,
        rate_hz_s=rate,
        training_intercept_rad=intercept,
    )
    return {
        "cfo_hz": cfo,
        "rate_hz_s": rate,
        "held_r": A.circular_r(error),
        "held_circular_rms_deg": float(np.degrees(np.sqrt(np.mean(error**2)))),
        "held_count": int(np.sum(held_mask)),
    }


def main() -> None:
    started = time.monotonic()
    selection = json.loads((REPORT / "selection.json").read_text())
    source = C.CachedReplayVisitSource(CACHE_INDEX, REPORT / "selection.json")
    starts = np.arange(0, 1_200_000 - 10_000 + 1, 20_000, dtype=np.int64)
    rows = []
    for position, selected in enumerate(selection["visits"], 1):
        visit = source.read_visit(selected["visit_index"])
        iq = np.column_stack((visit.complex64(0), visit.complex64(1)))
        valid = visit.valid_mask
        observations = A.direct_window_phasors(
            iq,
            valid,
            device_counter_start=selected["valid_start_counter"],
            sample_rate_hz=10_000_000,
            starts=starts,
            window_samples=10_000,
        )
        train_starts, held_starts = A.deterministic_holdout(
            observations.starts, f"20260926:{selected['visit_index']}:method24"
        )
        random_train = np.isin(observations.starts, train_starts)
        random_held = np.isin(observations.starts, held_starts)
        forward_train = np.arange(len(observations.starts)) < len(observations.starts) // 2
        forward_held = ~forward_train
        record = {
            **{
                key: selected[key]
                for key in (
                    "visit_index",
                    "target_index",
                    "channel",
                    "time_bin",
                    "split",
                    "valid_start_counter",
                )
            },
            "raw_phase_r": A.circular_r(np.angle(observations.phasors)),
            "median_coherence": float(np.median(observations.coherence)),
        }
        for degree, name in ((0, "raw"), (1, "constant_cfo"), (2, "cfo_rate")):
            for split_name, train, held in (
                ("random", random_train, random_held),
                ("forward", forward_train, forward_held),
            ):
                for key, value in _score_model(
                    observations.phasors,
                    observations.centers_counter,
                    train,
                    held,
                    selected,
                    degree,
                ).items():
                    record[f"{name}_{split_name}_{key}"] = value
        rows.append(record)
        if position % 8 == 0:
            print(f"completed {position}/128", flush=True)
    output = HERE / "method24-direct-iq.csv"
    with output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "schema": "scan-phase-replay-dual-rx-direct/v1",
        "method_id": "24-direct-dual-rx-iq",
        "source_manifest_sha256": selection["input_manifest_sha256"],
        "cache_index_sha256": source.cache_index_sha256,
        "selection_sha256": (
            "sha256:b73c0d5322a6a70c6ee851ee80ad99ef62ca13b190ae4bdeb35ce95ce2030115"
        ),
        "validity_policy": (
            "all RF-valid after full audit found zero counter words; "
            "digest verification repeated per selected chunk"
        ),
        "window": {"samples": 10_000, "stride_samples": 20_000, "count_per_visit": 60},
        "wrong_time_control_offset_samples": 130_000,
        "counts": {
            "eligible": 128,
            "attempted": len(rows),
            "evaluation": sum(r["split"] == "evaluation" for r in rows),
        },
        "medians": {
            key: float(np.median([r[key] for r in rows if r["split"] == "evaluation"]))
            for key in (
                "raw_phase_r",
                "median_coherence",
                "raw_random_held_r",
                "constant_cfo_random_held_r",
                "cfo_rate_random_held_r",
                "raw_forward_held_r",
                "constant_cfo_forward_held_r",
                "cfo_rate_forward_held_r",
            )
        },
        "runtime_wall_seconds": time.monotonic() - started,
        "output_sha256": _digest(output.read_bytes()),
    }
    (HERE / "method24-summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
