#!/usr/bin/env python3
"""Bounded saved-DS5 native GLRT search; never opens a radio or archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
from contextlib import ExitStack
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
DATASET = REPORT / "dataset"
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
sys.path[:0] = [str(DEPLOY), str(DEPLOY / "src")]

from tools.native_presence import build_dwell_presence  # noqa: E402
from tools.presence_dwell import NativeDwell, unpack  # noqa: E402


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def expected_digest(value: str) -> str:
    if value.startswith("sha256:"):
        value = value.removeprefix("sha256:")
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("invalid SHA-256 field")
    return value


def array_digest(values: np.ndarray) -> str:
    return hashlib.sha256(memoryview(np.ascontiguousarray(values))).hexdigest()


def write_new(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def gated(candidate: dict, threshold: float = 0.025) -> bool:
    return bool(candidate["fractional_complete"] and candidate["margin"] > threshold)


def circular_epoch_difference_us(a: dict, b: dict, rate: int) -> float:
    period = rate / 750.0
    a_epoch = a["epoch"] + a["fractional_offset_samples"]
    b_epoch = b["epoch"] + b["fractional_offset_samples"]
    delta = (a_epoch - b_epoch) % period
    return min(delta, period - delta) / rate * 1e6


def candidates_match(actual: dict, expected: dict, rate: int, policy: dict) -> bool:
    return (
        (not policy["require_same_window"] or actual["window_index"] == expected["window_index"])
        and abs(actual["tracking_cfo_hz"] - expected["tracking_cfo_hz"])
        <= policy["maximum_cfo_difference_hz"]
        and circular_epoch_difference_us(actual, expected, rate)
        <= policy["maximum_circular_epoch_difference_us"]
    )


def candidate_identity(candidate: dict) -> dict:
    return {
        "window_index": candidate["window_index"],
        "epoch": candidate["epoch"],
        "fractional_offset_samples": candidate["fractional_offset_samples"],
        "epoch_with_fractional_samples": candidate["epoch"]
        + candidate["fractional_offset_samples"],
        "tracking_cfo_hz": candidate["tracking_cfo_hz"],
    }


def compare_candidate_inventories(
    actual: list[dict], expected: list[dict], rate: int, policy: dict
) -> dict:
    expected_positive = [candidate for candidate in expected if gated(candidate)]
    actual_positive = [candidate for candidate in actual if gated(candidate)]
    matches = []
    matched_actual = set()
    for reference_index, reference in enumerate(expected_positive):
        compatible = [
            (actual_index, candidate)
            for actual_index, candidate in enumerate(actual_positive)
            if actual_index not in matched_actual
            and candidates_match(candidate, reference, rate, policy)
        ]
        if not compatible:
            continue
        actual_index, candidate = min(
            compatible,
            key=lambda pair: circular_epoch_difference_us(pair[1], reference, rate),
        )
        matched_actual.add(actual_index)
        matches.append(
            {
                "reference_index": reference_index,
                "actual_index": actual_index,
                "reference_identity": candidate_identity(reference),
                "actual_identity": candidate_identity(candidate),
                "cfo_delta_hz": candidate["tracking_cfo_hz"]
                - reference["tracking_cfo_hz"],
                "circular_epoch_delta_us": circular_epoch_difference_us(
                    candidate, reference, rate
                ),
                "exact_score_delta": candidate["exact_score"] - reference["exact_score"],
                "control_score_delta": candidate["control_score"]
                - reference["control_score"],
                "margin_delta": candidate["margin"] - reference["margin"],
            }
        )
    return {
        "reference_positive_candidates": len(expected_positive),
        "actual_positive_candidates": len(actual_positive),
        "matched_reference_candidates": len(matches),
        "lost_reference_candidates": len(expected_positive) - len(matches),
        "additional_positive_candidates": len(actual_positive) - len(matched_actual),
        "case_retained": bool(expected_positive) and bool(matches),
        "matches": matches,
    }


def compare_constructed_pilot(candidates: list[dict], truth: dict | None, rx: int, rate: int):
    if not truth or not truth.get("starlink_model_present"):
        return None
    injected = truth["receivers"][rx]
    reference = {
        "window_index": injected["window"],
        "epoch": injected["epoch_samples"],
        "fractional_offset_samples": injected["fractional_delay_samples"],
        "tracking_cfo_hz": injected["cfo_hz"],
    }
    compatible = [
        candidate
        for candidate in candidates
        if gated(candidate)
        and candidates_match(
            candidate,
            reference,
            rate,
            {
                "maximum_cfo_difference_hz": 8000,
                "maximum_circular_epoch_difference_us": 2,
                "require_same_window": True,
            },
        )
    ]
    if not compatible:
        return {"injected": candidate_identity(reference), "matched": False}
    candidate = min(
        compatible, key=lambda value: circular_epoch_difference_us(value, reference, rate)
    )
    return {
        "injected": candidate_identity(reference),
        "matched": True,
        "actual": candidate_identity(candidate),
        "cfo_delta_hz": candidate["tracking_cfo_hz"] - reference["tracking_cfo_hz"],
        "circular_epoch_delta_us": circular_epoch_difference_us(candidate, reference, rate),
    }


def compact_result(value, source: str) -> dict:
    result = unpack(value)
    window = result["rank"]["order"][0]
    confirmation = result["confirmations"][0]
    candidates = []
    for candidate in confirmation["candidates"][: confirmation["candidate_count"]]:
        candidates.append(
            {
                "source": source,
                "window_index": window,
                "epoch": candidate["epoch"],
                "fractional_offset_samples": candidate["fractional_offset_samples"],
                "tracking_cfo_hz": candidate["tracking_cfo_hz"],
                "acquired_cfo_hz": candidate["acquired_cfo_hz"],
                "fractional_complete": candidate["fractional_complete"],
                "exact_score": candidate["exact_score"],
                "control_score": candidate["control_score"],
                "margin": candidate["margin"],
                "conditioned_score": candidate["conditioned_score"],
                "coarse_score": candidate["coarse_score"],
            }
        )
    return {
        "candidates": candidates,
        "native_cpu_ms": result["total_cpu_ms"],
        "native_wall_ms": result["total_wall_ms"],
        "rank": {
            "scores": result["rank"]["scores"],
            "order": result["rank"]["order"],
            "projected_epoch_samples": result["rank"]["projected_epoch_samples"],
            "total_cpu_ms": result["rank"]["total_cpu_ms"],
        },
        "timing_proposal": result["timing_proposals"][0],
    }


class Runner:
    def __init__(self, workspaces: dict[str, NativeDwell], variant: dict):
        self.workspaces = workspaces
        self.variant = variant

    def __call__(self, iq: np.ndarray) -> dict:
        started_wall = time.perf_counter_ns()
        started_cpu = time.process_time_ns()
        candidates, calls = [], []
        for step in self.variant["steps"]:
            if step == "blind_if_no_gate":
                if any(gated(c) for c in candidates):
                    continue
                primitive, seeded = "blind", False
            else:
                primitive, seeded = step, step != "blind"
            call = compact_result(
                self.workspaces[primitive].run(iq, maximum=1, seeded=seeded), primitive
            )
            candidates.extend(call["candidates"])
            calls.append(call)
        return {
            "candidates": candidates,
            "calls": calls,
            "native_cpu_ms": sum(c["native_cpu_ms"] for c in calls),
            "native_wall_ms": sum(c["native_wall_ms"] for c in calls),
            "process_cpu_ms": (time.process_time_ns() - started_cpu) / 1e6,
            "wall_ms": (time.perf_counter_ns() - started_wall) / 1e6,
        }


def load_config(path: Path, split: str) -> dict:
    config = json.loads(path.read_text())
    if config["schema"] != "org.leo.research.ds5-server-search-config/v1":
        raise ValueError("unexpected search configuration schema")
    if split == "dev" and config["stage"] != "development_search":
        raise ValueError("development requires the development search configuration")
    if split == "control" and config["stage"] not in (
        "development_search",
        "frozen_validation",
    ):
        raise ValueError("controls require a development or frozen configuration")
    if split in ("validation", "holdout") and config["stage"] != "frozen_validation":
        raise ValueError("validation/holdout requires a frozen configuration")
    if config["warmups"] != 1 or config["timed_repetitions"] != 3:
        raise ValueError("experiment requires one warmup and three timed repetitions")
    if config["gate"] != {
        "fractional_complete": True,
        "margin_strictly_greater_than": 0.025,
    }:
        raise ValueError("unreviewed positive gate")
    names = [variant["name"] for variant in config["variants"]]
    if len(names) != len(set(names)) or "baseline_blind_512" not in names:
        raise ValueError("unique variants and exact blind baseline required")
    return config


def load_cases(path: Path, split: str) -> tuple[list[dict], dict]:
    raw = json.loads(path.read_text())
    cases = raw["cases"] if isinstance(raw, dict) else raw
    selected = [case for case in cases if case["split"] == split]
    rates = {}
    for case in selected:
        rates[str(case["rate_hz"])] = rates.get(str(case["rate_hz"]), 0) + 1
    return selected, {"all_case_count": len(cases), "selected_by_rate": rates}


def load_iq(case: dict, dataset_dir: Path) -> np.ndarray:
    path = (dataset_dir / case["raw_npy"]["path"]).resolve()
    if not path.is_relative_to(dataset_dir.resolve()):
        raise ValueError("raw IQ path escapes dataset directory")
    if digest(path) != expected_digest(case["raw_npy"]["sha256"]):
        raise ValueError(f"IQ hash mismatch: {case['case_id']}")
    values = np.load(path, allow_pickle=False)
    expected = (case["rate_hz"] * 120 // 1000, 2, 2)
    if values.dtype != np.dtype("<i2") or values.shape != expected:
        raise ValueError(f"unexpected IQ geometry: {case['case_id']}")
    return values


def ensure_library(config: dict) -> Path:
    library = HERE / "native_dwell.so"
    receipt = library.with_name(library.name + ".build.json")
    if library.exists() != receipt.exists():
        raise ValueError("partial native build artifact")
    if library.exists():
        build = json.loads(receipt.read_text())
        if digest(library) != build["binary_sha256"]:
            raise ValueError("cached native binary does not match its build receipt")
        for relative, expected in build["sources_sha256"].items():
            source = DEPLOY / relative
            if not source.is_file() or digest(source) != expected:
                raise ValueError(f"cached native source changed: {relative}")
        for absolute, expected in build.get("dependencies_sha256", {}).items():
            dependency = Path(absolute)
            if not dependency.is_file() or digest(dependency) != expected:
                raise ValueError(f"cached native dependency changed: {absolute}")
        return library
    protocol_path = DEPLOY / "config/analysis/arm-presence-native-tone-ci16-v1.json"
    protocol = json.loads(protocol_path.read_text())
    flags = tuple(protocol["common_flags"]) + tuple(
        f"-DLEO_PRESENCE_{key}={value}"
        for key, value in protocol["variants"][0]["defines"].items()
    )
    return build_dwell_presence(library, cflags=flags)


def make_workspaces(stack: ExitStack, library: Path, rate: int, edge: str, config: dict):
    low, high = config["timing_bins_by_rate"][str(rate)]
    return {
        "blind": stack.enter_context(NativeDwell(library, rate, edge, 512)),
        "seed_512": stack.enter_context(NativeDwell(library, rate, edge, 512)),
        "seed_low": stack.enter_context(NativeDwell(library, rate, edge, 512, low)),
        "seed_high": stack.enter_context(NativeDwell(library, rate, edge, 512, high)),
    }


def summarize(rows: list[dict], config: dict) -> dict:
    def one(subset: list[dict]) -> dict:
        reference_positive = 0
        retained = 0
        reference_candidates = 0
        retained_candidates = 0
        gated_outputs = 0
        new_gated_outputs = 0
        constructed_pilot_cases = 0
        constructed_pilot_matches = 0
        for row in subset:
            actual = [c for c in row["representative"]["candidates"] if gated(c)]
            gated_outputs += bool(actual)
            comparison = row["comparison_to_blind"]
            new_gated_outputs += bool(actual) and not bool(
                comparison["reference_positive_candidates"]
            )
            reference_candidates += comparison["reference_positive_candidates"]
            retained_candidates += comparison["matched_reference_candidates"]
            if comparison["reference_positive_candidates"]:
                reference_positive += 1
                if comparison["case_retained"]:
                    retained += 1
            if row["constructed_truth_comparison"] is not None:
                constructed_pilot_cases += 1
                constructed_pilot_matches += row["constructed_truth_comparison"]["matched"]
        return {
            "receiver_cases": len(subset),
            "baseline_positive_receiver_cases": reference_positive,
            "identity_retained_receiver_cases": retained,
            "identity_retention_fraction": retained / reference_positive
            if reference_positive
            else None,
            "baseline_positive_candidates": reference_candidates,
            "identity_retained_candidates": retained_candidates,
            "candidate_identity_retention_fraction": retained_candidates
            / reference_candidates
            if reference_candidates
            else None,
            "gated_output_receiver_cases": gated_outputs,
            "new_gated_vs_blind_receiver_cases": new_gated_outputs,
            "constructed_pilot_receiver_cases": constructed_pilot_cases,
            "constructed_pilot_identity_matches": constructed_pilot_matches,
            "constructed_pilot_recovery_fraction": constructed_pilot_matches
            / constructed_pilot_cases
            if constructed_pilot_cases
            else None,
            "median_of_case_median_native_cpu_ms": statistics.median(
                row["timing_median"]["native_cpu_ms"] for row in subset
            )
            if subset
            else None,
            "median_of_case_median_wall_ms": statistics.median(
                row["timing_median"]["wall_ms"] for row in subset
            )
            if subset
            else None,
        }
    summaries = {}
    groups = sorted({(row["origin"], row.get("control_kind")) for row in rows})
    for variant in config["variants"]:
        name = variant["name"]
        subset = [row for row in rows if row["variant"] == name]
        summaries[name] = {
            "overall": one(subset),
            "by_origin_control": {
                f"{origin}:{control or 'none'}": one(
                    [
                        row
                        for row in subset
                        if (row["origin"], row.get("control_kind")) == (origin, control)
                    ]
                )
                for origin, control in groups
            },
        }
    return summaries


def evaluate(args) -> dict:
    config_path = args.config.resolve()
    output = args.output.resolve()
    if not output.is_relative_to(HERE) or output.exists():
        raise ValueError("new output must be beneath the owned search directory")
    if args.split == "holdout" and not args.authorize_holdout:
        raise ValueError("holdout requires explicit --authorize-holdout")
    config = load_config(config_path, args.split)
    cases_path = args.dataset.resolve() / "cases.json"
    cases, inventory = load_cases(cases_path, args.split)
    library = ensure_library(config)
    supported = set(config["supported_rates_hz"])
    rows = []
    unsupported = []
    with ExitStack() as stack:
        workspaces = {}
        for case in cases:
            rate = case["rate_hz"]
            if rate not in supported:
                unsupported.append(
                    {"case_id": case["case_id"], "rate_hz": rate, "status": "unsupported"}
                )
                continue
            iq = load_iq(case, args.dataset)
            key = (rate, case["edge"])
            if key not in workspaces:
                workspaces[key] = make_workspaces(stack, library, *key, config)
            runners = {
                variant["name"]: Runner(workspaces[key], variant)
                for variant in config["variants"]
            }
            for rx in range(2):
                values = np.ascontiguousarray(iq[:, rx, :])
                input_sha256 = array_digest(values)
                for runner in runners.values():
                    for _ in range(config["warmups"]):
                        runner(values)
                samples = {name: [] for name in runners}
                for repetition in range(config["timed_repetitions"]):
                    names = list(runners)
                    if repetition % 2:
                        names.reverse()
                    for name in names:
                        result = runners[name](values)
                        result["repetition"] = repetition
                        samples[name].append(result)
                for name, values_by_repeat in samples.items():
                    first_candidates = values_by_repeat[0]["candidates"]
                    if any(v["candidates"] != first_candidates for v in values_by_repeat[1:]):
                        raise ValueError(
                            f"nondeterministic candidates: {case['case_id']} rx {rx} {name}"
                        )
                    representative = sorted(values_by_repeat, key=lambda x: x["wall_ms"])[1]
                    rows.append(
                        {
                            "case_id": case["case_id"],
                            "origin": case["origin"],
                            "control_kind": case.get("test_stratum")
                            or case.get("control_kind")
                            or case.get("synthetic_kind")
                            or case.get("truth", {}).get("kind"),
                            "truth_status": case.get("truth_status"),
                            "truth": case.get("truth"),
                            "session_id": case.get("session_id"),
                            "visit_index": case.get("visit_index"),
                            "channel": case.get("channel"),
                            "rate_hz": rate,
                            "edge": case["edge"],
                            "rx": rx,
                            "source_start_counter": str(case.get("source_start_counter", "")),
                            "input_sha256": input_sha256,
                            "variant": name,
                            "timing_samples": [
                                {
                                    "repetition": v["repetition"],
                                    "native_cpu_ms": v["native_cpu_ms"],
                                    "native_wall_ms": v["native_wall_ms"],
                                    "process_cpu_ms": v["process_cpu_ms"],
                                    "wall_ms": v["wall_ms"],
                                    "candidates": v["candidates"],
                                }
                                for v in values_by_repeat
                            ],
                            "timing_median": {
                                metric: statistics.median(v[metric] for v in values_by_repeat)
                                for metric in (
                                    "native_cpu_ms",
                                    "native_wall_ms",
                                    "process_cpu_ms",
                                    "wall_ms",
                                )
                            },
                            "representative": representative,
                        }
                    )
                if array_digest(values) != input_sha256:
                    raise ValueError(f"native evaluation mutated caller IQ: {case['case_id']} rx {rx}")
    blind = {
        (row["case_id"], row["rx"]): row["representative"]["candidates"]
        for row in rows
        if row["variant"] == "baseline_blind_512"
    }
    for row in rows:
        row["comparison_to_blind"] = compare_candidate_inventories(
            row["representative"]["candidates"],
            blind[(row["case_id"], row["rx"])],
            row["rate_hz"],
            config["identity_match"],
        )
        row["constructed_truth_comparison"] = compare_constructed_pilot(
            row["representative"]["candidates"],
            row["truth"],
            row["rx"],
            row["rate_hz"],
        )
    receipt = {
        "schema": "org.leo.research.ds5-server-search-results/v1",
        "split": args.split,
        "status": "diagnostic_baseline_retention_not_classifier_recall",
        "scope": config["scope"],
        "config_sha256": digest(config_path),
        "experiment_script_sha256": digest(Path(__file__)),
        "dataset_cases_sha256": digest(cases_path),
        "native_binary_sha256": digest(library),
        "native_build_receipt": json.loads(
            library.with_name(library.name + ".build.json").read_text()
        ),
        "deploy_git_head": subprocess.run(
            ["git", "-C", str(DEPLOY), "rev-parse", "HEAD"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip(),
        "source_sha256": {
            str(path.relative_to(DEPLOY)): digest(path)
            for path in (
                DEPLOY / "tools/native_presence.py",
                DEPLOY / "tools/presence_dwell.py",
                DEPLOY / "tools/presence_window_rank.py",
                DEPLOY / "src/leo/analysis/native_presence/presence.c",
                DEPLOY / "src/leo/analysis/native_presence/dwell.c",
                DEPLOY / "src/leo/analysis/native_presence/window_rank.c",
                DEPLOY / "src/leo/analysis/starlink/templates.py",
            )
        },
        "host": platform.uname()._asdict(),
        "inventory": inventory,
        "unsupported": unsupported,
        "rows": rows,
        "summary": summarize(rows, config),
        "limitations": [
            "blind-positive identity retention is diagnostic and is not truth, recall, or an absence claim",
            "composite variants rerun the 512-bin screen in the current research binding; a fused implementation can share it",
            "desktop timings exclude queueing, capture, transport, and ARM execution",
            "7.5 and 10 MS/s are reported unsupported rather than snapped or resampled",
        ],
    }
    write_new(output, receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--split", choices=("dev", "control", "validation", "holdout"), required=True
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--authorize-holdout", action="store_true")
    args = parser.parse_args()
    result = evaluate(args)
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
