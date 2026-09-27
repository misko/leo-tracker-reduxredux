#!/usr/bin/env python3
"""Run one frozen FP64 versus FP32 detector comparison on adversarial controls."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import signal
import sys
from contextlib import ExitStack
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent.parent
CONTROL = REPORT / "lag3_controls"
NATIVE = REPORT / "native"
BASELINE = NATIVE / "libblind_strided_v4.so"
CANDIDATE = REPORT / "fft32" / "libfft32_fftw.so"
RUNTIME_FFTW = Path("/usr/lib/x86_64-linux-gnu/libfftw3f.so.3.6.10")
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
sys.path[:0] = [
    str(REPORT),
    str(NATIVE),
    str(REPORT / "lag3_validation"),
    str(DEPLOY),
    str(DEPLOY / "src"),
]

from blind_strided_v4 import NativeStridedBlindV4  # noqa: E402
from score import score_case  # noqa: E402
from tools.presence_dwell import NativeDwell  # noqa: E402
from tracking import Observation, circular_samples, reference_match  # noqa: E402


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return "sha256:" + value.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def verify_source_lock() -> dict:
    lock = load_json(HERE / "source_lock.json")
    paths = {
        "design": HERE / "design.json",
        "adapter": Path(__file__),
        "challenge_cases": CONTROL / "cases.json",
        "challenge_design": CONTROL / "design.json",
        "challenge_source_lock": CONTROL / "source_lock.json",
        "challenge_builder": CONTROL / "build_controls.py",
        "baseline_library": BASELINE,
        "baseline_build_receipt": BASELINE.with_name(BASELINE.name + ".build.json"),
        "candidate_library": CANDIDATE,
        "candidate_build_receipt": CANDIDATE.with_name(CANDIDATE.name + ".build.json"),
        "runtime_fftw": RUNTIME_FFTW,
        "native_wrapper": NATIVE / "blind_strided_v4.py",
        "native_c": NATIVE / "blind_strided_v4.c",
        "native_header": NATIVE / "blind_strided_v4.h",
        "native_profile": NATIVE / "profile.json",
        "tracking": REPORT / "tracking.py",
        "truth_scorer": REPORT / "lag3_validation" / "score.py",
    }
    actual = {name: digest(path) for name, path in paths.items()}
    if lock.get("files") != actual:
        raise ValueError("frozen adversarial-transfer input changed")
    return lock


def select_cases(payload: dict, recipes: dict) -> list[tuple[dict, dict]]:
    by_id = {case["case_id"]: case for case in payload["cases"]}
    recipe_by_id = {case["case_id"]: case for case in recipes["cases"]}
    if set(by_id) != set(recipe_by_id) or len(by_id) != 20:
        raise ValueError("unexpected adversarial challenge membership")
    selected = [(by_id[case_id], recipe_by_id[case_id]) for case_id in sorted(by_id)]
    if {case["rate_hz"] for case, _ in selected} != {2_500_000, 5_000_000}:
        raise ValueError("unexpected challenge rates")
    return selected


def load_iq(case: dict) -> np.ndarray:
    path = (CONTROL / case["raw_npy"]["path"]).resolve()
    if not path.is_relative_to(CONTROL.resolve()):
        raise ValueError("IQ path escapes challenge directory")
    if digest(path) != case["raw_npy"]["sha256"]:
        raise ValueError(f"IQ hash mismatch: {case['case_id']}")
    values = np.load(path, mmap_mode="r", allow_pickle=False)
    expected = (case["rate_hz"] * case["dwell_ms"] // 1000, 2, 2)
    if values.dtype != np.dtype("<i2") or values.shape != expected:
        raise ValueError(f"IQ geometry mismatch: {case['case_id']}")
    return values


def proposals(result) -> list[dict]:
    output = []
    for confirmation_index in range(int(result.confirmation_count)):
        confirmation = result.confirmations[confirmation_index]
        window = int(result.rank.order[confirmation_index])
        for candidate_index in range(int(confirmation.candidate_count)):
            candidate = confirmation.candidates[candidate_index]
            exact = float(candidate.exact_score)
            control = float(candidate.control_score)
            supported = bool(candidate.fractional_complete)
            output.append(
                {
                    "window": window,
                    "epoch_samples": float(
                        candidate.epoch + candidate.fractional_offset_samples
                    ),
                    "cfo_hz": float(candidate.tracking_cfo_hz),
                    "scoring_cfo_hz": float(candidate.acquired_cfo_hz),
                    "exact_score": exact,
                    "control_score": control,
                    "margin": exact - control,
                    "supported": supported,
                    "positive": supported and exact - control > 0.025,
                }
            )
    return output


def compact(result) -> dict:
    candidate_proposals = proposals(result)
    return {
        "selected_window": int(result.rank.order[0]),
        "rank_order": [int(value) for value in result.rank.order],
        "projected_epoch_samples": [int(value) for value in result.rank.projected_epoch_samples],
        "rank_scores": [float(value) for value in result.rank.scores],
        "confirmation_count": int(result.confirmation_count),
        "proposals": candidate_proposals,
        "positive": bool(candidate_proposals and candidate_proposals[0]["positive"]),
    }


def as_observation(value: dict | None) -> Observation | None:
    if value is None:
        return None
    return Observation(
        window=value["window"],
        epoch_samples=value["epoch_samples"],
        cfo_hz=value["cfo_hz"],
        exact=value["exact_score"],
        control=value["control_score"],
        supported=value["supported"],
        scoring_cfo_hz=value["scoring_cfo_hz"],
    )


def compare(reference: dict, candidate: dict, rate_hz: int) -> dict:
    reference_first = reference["proposals"][0] if reference["proposals"] else None
    candidate_first = candidate["proposals"][0] if candidate["proposals"] else None
    reference_observation = as_observation(reference_first)
    candidate_observation = as_observation(candidate_first)
    matched = bool(
        reference_observation
        and candidate_observation
        and reference_match(reference_observation, candidate_observation, rate_hz)
    )
    delta = None
    if reference_first is not None and candidate_first is not None:
        sample_delta = (
            (reference_first["window"] - candidate_first["window"]) * (rate_hz // 50)
            + reference_first["epoch_samples"]
            - candidate_first["epoch_samples"]
        )
        delta = {
            "circular_timing_error_us": abs(circular_samples(sample_delta, rate_hz))
            / rate_hz
            * 1e6,
            "cfo_error_hz": abs(reference_first["cfo_hz"] - candidate_first["cfo_hz"]),
            "exact_delta": candidate_first["exact_score"] - reference_first["exact_score"],
            "control_delta": (
                candidate_first["control_score"] - reference_first["control_score"]
            ),
            "margin_delta": candidate_first["margin"] - reference_first["margin"],
        }
    rank_deltas = [
        candidate_score - reference_score
        for reference_score, candidate_score in zip(
            reference["rank_scores"], candidate["rank_scores"], strict=True
        )
    ]
    return {
        "matched_positive_reference": matched,
        "lost_positive_reference": reference["positive"] and not matched,
        "additional_candidate_positive": candidate["positive"] and not matched,
        "selected_window_changed": (
            reference["selected_window"] != candidate["selected_window"]
        ),
        "rank_order_changed": reference["rank_order"] != candidate["rank_order"],
        "projected_epochs_changed": (
            reference["projected_epoch_samples"] != candidate["projected_epoch_samples"]
        ),
        "max_abs_rank_score_delta": max(abs(value) for value in rank_deltas),
        "first_proposal_delta": delta,
    }


def summarize(rows: list[dict]) -> dict:
    paired = [
        row["comparison"]["first_proposal_delta"]
        for row in rows
        if row["comparison"]["first_proposal_delta"] is not None
    ]
    trajectory_ids = sorted(
        {
            trajectory
            for row in rows
            for side in ("reference_truth", "candidate_truth")
            for trajectory in row[side]["each_injected_pilot_supported"]
        }
    )
    return {
        "receiver_cases": len(rows),
        "reference_positive": sum(row["reference"]["positive"] for row in rows),
        "candidate_positive": sum(row["candidate"]["positive"] for row in rows),
        "matched_reference_positive": sum(
            row["comparison"]["matched_positive_reference"] for row in rows
        ),
        "lost_reference_positive": sum(
            row["comparison"]["lost_positive_reference"] for row in rows
        ),
        "additional_candidate_positive": sum(
            row["comparison"]["additional_candidate_positive"] for row in rows
        ),
        "selected_window_changes": sum(
            row["comparison"]["selected_window_changed"] for row in rows
        ),
        "rank_order_changes": sum(row["comparison"]["rank_order_changed"] for row in rows),
        "projected_epoch_array_changes": sum(
            row["comparison"]["projected_epochs_changed"] for row in rows
        ),
        "maximum_first_proposal_timing_error_us": (
            max(value["circular_timing_error_us"] for value in paired) if paired else None
        ),
        "maximum_first_proposal_cfo_error_hz": (
            max(value["cfo_error_hz"] for value in paired) if paired else None
        ),
        "maximum_rank_score_delta": max(
            row["comparison"]["max_abs_rank_score_delta"] for row in rows
        ),
        "constructed_truth": {
            side: {
                "pilot_truth_receiver_cases": sum(
                    row[f"{side}_truth"]["pilot_truth_count"] > 0 for row in rows
                ),
                "any_coordinate_match": sum(
                    row[f"{side}_truth"]["any_coordinate_match"] is True for row in rows
                ),
                "any_supported_coordinate_match": sum(
                    row[f"{side}_truth"]["any_supported_coordinate_match"] is True
                    for row in rows
                ),
                "supported_trajectory_matches": {
                    trajectory: sum(
                        row[f"{side}_truth"]["each_injected_pilot_supported"].get(
                            trajectory, False
                        )
                        for row in rows
                    )
                    for trajectory in trajectory_ids
                },
            }
            for side in ("reference", "candidate")
        },
    }


def run() -> dict:
    signal.alarm(180)
    lock = verify_source_lock()
    payload = load_json(CONTROL / "cases.json")
    design = load_json(CONTROL / "design.json")
    selected = select_cases(payload, design)
    rows: list[dict] = []
    geometries = {(case["rate_hz"], case["edge"]) for case, _ in selected}
    with ExitStack() as stack:
        references = {
            geometry: stack.enter_context(NativeDwell(BASELINE, *geometry, 512))
            for geometry in geometries
        }
        candidates = {
            geometry: stack.enter_context(
                NativeStridedBlindV4(*geometry, library=CANDIDATE, bins=512)
            )
            for geometry in geometries
        }
        for case, recipe in selected:
            iq = load_iq(case)
            memory_hash = hashlib.sha256(iq).hexdigest()
            geometry = (case["rate_hz"], case["edge"])
            for rx in range(2):
                reference_result = references[geometry].run(
                    np.ascontiguousarray(iq[:, rx, :]), maximum=1, seeded=False
                )
                candidate_result = candidates[geometry].run(
                    iq[:, rx, :], maximum=1, seeded=False
                )
                reference = compact(reference_result)
                candidate = compact(candidate_result)
                rows.append(
                    {
                        "case_id": case["case_id"],
                        "rx": rx,
                        "rate_hz": case["rate_hz"],
                        "edge": case["edge"],
                        "kind": recipe["kind"],
                        "raw_sha256": case["raw_npy"]["sha256"],
                        "reference": reference,
                        "candidate": candidate,
                        "comparison": compare(reference, candidate, case["rate_hz"]),
                        "reference_truth": score_case(recipe, reference["proposals"]),
                        "candidate_truth": score_case(recipe, candidate["proposals"]),
                    }
                )
            if hashlib.sha256(iq).hexdigest() != memory_hash:
                raise ValueError("IQ changed in memory")
    if len(rows) != 40:
        raise ValueError("incomplete receiver-case schedule")
    by_rate_kind = {
        f"{rate}:{kind}": summarize(
            [row for row in rows if row["rate_hz"] == rate and row["kind"] == kind]
        )
        for rate in (2_500_000, 5_000_000)
        for kind in ("pilot", "noise", "tone", "two_pilot", "pilot_tone")
    }
    overall = summarize(rows)
    identity_gate_pass = all(
        overall[name] == 0
        for name in (
            "lost_reference_positive",
            "additional_candidate_positive",
            "selected_window_changes",
            "rank_order_changes",
        )
    )
    return {
        "schema": "org.leo.research.fft32-adversarial-transfer-result/v1",
        "scope": "science-only server comparison; no timing claim",
        "status": "complete",
        "design_sha256": digest(HERE / "design.json"),
        "source_lock_sha256": digest(HERE / "source_lock.json"),
        "frozen_sources": lock["files"],
        "candidate_seeded": False,
        "maximum_candidates": 1,
        "automatic_fallback": False,
        "performance_timing_valid": False,
        "association": {"timing_us": 2.0, "cfo_hz": 8000.0},
        "identity_gate_pass": identity_gate_pass,
        "summary": {"all": overall, "by_rate_kind": by_rate_kind},
        "rows": rows,
        "limitations": [
            "The FP64 detector is a numerical reference, not physical truth.",
            "Injected pilot presence does not require a positive detector label.",
            "Noise and tone proposals are not false alarms without a separate detector decision.",
            "Constructed Qin pilot-only controls are not physical ground truth beyond their injected components and omit unknown QAM/data and frequency-selective channels.",
            "This one-call science comparison makes no server, ARM, or pipeline timing claim.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "results.json")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.parent != HERE or output.exists():
        raise ValueError("output must be a new file directly beneath this report directory")
    payload = run()
    with output.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"identity_gate_pass": payload["identity_gate_pass"], **payload["summary"]["all"]}))


if __name__ == "__main__":
    main()
