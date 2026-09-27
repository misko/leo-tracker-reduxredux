"""Measure the frozen native rank scout on development and prior controls only."""

from __future__ import annotations

import argparse
import ctypes as ct
import hashlib
import json
import platform
import shutil
import signal
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
REFERENCE = REPORT / "dev_point_v1.json"
CONTROL_DATASET = REPORT.parent / "2026_09_26_ds5_server_eval" / "dataset"
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
sys.path[:0] = [str(DEPLOY), str(DEPLOY / "src")]

from tools.native_presence import build_dwell_presence  # noqa: E402
from tools.presence_window_rank import NativeWindowRank  # noqa: E402

RATES = (2_500_000, 5_000_000)
NATIVE_PROFILE = REPORT / "native" / "profile.json"


class SparseResult(ct.Structure):
    _fields_ = [
        ("window_scores", ct.c_double * 6),
        ("power_sum_score", ct.c_double),
        ("pairs_per_window", ct.c_uint32),
        ("cpu_ms", ct.c_double),
        ("wall_ms", ct.c_double),
    ]


class SparseScout:
    def __init__(self, library: Path, rate: int):
        self.rate = rate
        self.stride = {2_500_000: 8, 5_000_000: 16}[rate]
        self._library = ct.CDLL(str(library))
        self._run = self._library.scout_sparse_lag3_ci16
        self._run.argtypes = [
            ct.POINTER(ct.c_int16),
            ct.c_size_t,
            ct.c_uint32,
            ct.c_uint32,
            ct.POINTER(SparseResult),
        ]
        self._run.restype = ct.c_int

    def run(self, values: np.ndarray) -> SparseResult:
        if values.dtype != np.dtype("<i2") or values.shape != (
            self.rate * 120 // 1000,
            2,
        ):
            raise ValueError("sparse scout requires one packed 120 ms CI16 receiver")
        if not values.flags.c_contiguous:
            raise ValueError("sparse scout input must be contiguous")
        result = SparseResult()
        code = self._run(
            values.ctypes.data_as(ct.POINTER(ct.c_int16)),
            len(values),
            self.rate,
            self.stride,
            ct.byref(result),
        )
        if code:
            raise RuntimeError(f"sparse scout failed: {code}")
        return result


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return "sha256:" + value.hexdigest()


def array_digest(values: np.ndarray) -> str:
    return "sha256:" + hashlib.sha256(memoryview(np.ascontiguousarray(values))).hexdigest()


def load_json(path: Path, expected_sha256: str) -> dict:
    if digest(path) != expected_sha256:
        raise ValueError(f"frozen input hash mismatch: {path}")
    return json.loads(path.read_text())


def load_reference(payload: dict) -> dict[tuple[str, int], dict]:
    rows = {(row["case_id"], row["rx"]): row for row in payload["rows"]}
    positives = 0
    for row in rows.values():
        reference = row["reference"]
        recomputed = bool(
            reference["supported"] and reference["exact"] - reference["control"] > 0.025
        )
        if recomputed != row["reference_positive"]:
            raise ValueError("reference positive gate mismatch")
        positives += recomputed
    if len(rows) != 256 or positives != 36:
        raise ValueError("unexpected development reference inventory")
    return rows


def select_cases(payload: dict, split: str, *, controls: bool = False) -> list[dict]:
    if controls:
        selected = [
            case
            for case in payload["cases"]
            if case["origin"] == "synthetic_control" and case["rate_hz"] in RATES
        ]
        if len(selected) != 12:
            raise ValueError("unexpected prior synthetic control inventory")
        return selected
    selected = [case for case in payload["cases"] if case["split"] == split]
    if split != "dev" or len(selected) != 128:
        raise ValueError("scout is restricted to the 128 development visits")
    return selected


def load_iq(root: Path, case: dict) -> np.ndarray:
    path = (root / case["raw_npy"]["path"]).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("IQ path escapes dataset root")
    if digest(path) != case["raw_npy"]["sha256"]:
        raise ValueError(f"IQ hash mismatch: {case['case_id']}")
    values = np.load(path, allow_pickle=False, mmap_mode="r")
    expected = (case["rate_hz"] * 120 // 1000, 2, 2)
    if values.dtype != np.dtype("<i2") or values.shape != expected:
        raise ValueError(f"IQ geometry mismatch: {case['case_id']}")
    return values


def ensure_rank_library(design: dict) -> Path:
    library = HERE / "native_rank.so"
    receipt = library.with_name(library.name + ".build.json")
    if library.exists() != receipt.exists():
        raise ValueError("partial native rank build")
    if library.exists():
        build = json.loads(receipt.read_text())
        if digest(library).removeprefix("sha256:") != build["binary_sha256"]:
            raise ValueError("cached native rank binary mismatch")
        for relative, expected in build["sources_sha256"].items():
            source = DEPLOY / relative
            if not source.is_file() or digest(source).removeprefix("sha256:") != expected:
                raise ValueError(f"cached source changed: {relative}")
        return library
    profile = load_json(NATIVE_PROFILE, design["native_profile_sha256"])
    flags = tuple(profile["flags"])
    return build_dwell_presence(library, cflags=flags)


def ensure_sparse_library() -> Path:
    source = HERE / "sparse_lag.c"
    library = HERE / "sparse_lag.so"
    receipt = library.with_name(library.name + ".build.json")
    if library.exists() != receipt.exists():
        raise ValueError("partial sparse scout build")
    source_sha256 = digest(source).removeprefix("sha256:")
    if library.exists():
        build = json.loads(receipt.read_text())
        if build["source_sha256"] != source_sha256:
            raise ValueError("cached sparse scout source changed")
        if digest(library).removeprefix("sha256:") != build["binary_sha256"]:
            raise ValueError("cached sparse scout binary mismatch")
        return library
    compiler = shutil.which("cc")
    if compiler is None:
        raise FileNotFoundError("cc")
    command = [
        compiler,
        "-std=c11",
        "-O3",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-shared",
        "-fPIC",
        str(source),
        "-lm",
        "-o",
        str(library),
    ]
    subprocess.run(command, check=True)
    build = {
        "schema": "org.leo.research.ds5-cached-sparse-scout-build.v1",
        "command": command,
        "compiler_version": subprocess.run(
            [compiler, "--version"], check=True, text=True, capture_output=True
        ).stdout,
        "compiler_sha256": digest(Path(compiler).resolve()).removeprefix("sha256:"),
        "source_sha256": source_sha256,
        "binary_sha256": digest(library).removeprefix("sha256:"),
    }
    with receipt.open("x") as stream:
        json.dump(build, stream, indent=2)
        stream.write("\n")
    return library


def screen_statistics(result) -> tuple[float, float]:
    scores = [float(value) for value in result.scores]
    order = [int(value) for value in result.order]
    maximum = scores[order[0]]
    second = scores[order[1]]
    return maximum, maximum / max(second, 1e-300)


def threshold_for_full_retention(rows: list[dict], statistic: str) -> float:
    positive = [row[statistic] for row in rows if row["reference_positive"]]
    if len(positive) != 36 or not all(np.isfinite(value) for value in positive):
        raise ValueError("threshold requires all 36 finite development positives")
    return min(positive)


def summarize_variant(
    rows: list[dict], statistic: str, threshold: float, timing_field: str
) -> dict:
    routed = [row for row in rows if row[statistic] >= threshold]
    positive = [row for row in rows if row["reference_positive"]]
    retained = [row for row in positive if row[statistic] >= threshold]
    by_rate = {}
    for rate in RATES:
        subset = [row for row in rows if row["rate_hz"] == rate]
        rate_routed = [row for row in subset if row[statistic] >= threshold]
        rate_positive = [row for row in subset if row["reference_positive"]]
        by_rate[str(rate)] = {
            "receiver_visits": len(subset),
            "reference_positives": len(rate_positive),
            "routed": len(rate_routed),
            "route_fraction": len(rate_routed) / len(subset) if subset else None,
            "threshold_transfer_status": (
                "development_supported" if rate_positive else "unverified_no_dev_positives"
            ),
        }
    baseline_total = sum(row["baseline_cpu_ms"] for row in rows)
    routed_baseline = sum(row["baseline_cpu_ms"] for row in routed)
    scout_total = sum(row[timing_field] for row in rows)
    return {
        "statistic": statistic,
        "inclusive_threshold": threshold,
        "receiver_visits": len(rows),
        "reference_positives": len(positive),
        "retained_reference_positives": len(retained),
        "reference_relative_retention": len(retained) / len(positive),
        "routed": len(routed),
        "route_fraction": len(routed) / len(rows),
        "measured_screen_negative": len(rows) - len(routed),
        "by_rate": by_rate,
        "optimistic_cost_ceiling": {
            "baseline_cpu_ms": baseline_total,
            "scout_cpu_ms": scout_total,
            "routed_baseline_cpu_ms": routed_baseline,
            "speedup_if_every_route_runs_baseline_and_nonroutes_stop": baseline_total
            / (scout_total + routed_baseline),
            "zero_cost_scout_speedup_ceiling": baseline_total / routed_baseline,
        },
    }


def summarize_controls(rows: list[dict], thresholds: dict[str, float]) -> dict:
    result = {}
    for name, statistic in (
        ("rank_max_score", "score_max"),
        ("sparse_lag3_power", "sparse_power"),
    ):
        threshold = thresholds[name]
        groups = {}
        for rate in RATES:
            for kind in ("pilot", "noise", "tone"):
                subset = [
                    row for row in rows if row["rate_hz"] == rate and row["truth_kind"] == kind
                ]
                groups[f"{rate}:{kind}"] = {
                    "receiver_cases": len(subset),
                    "routed": sum(row[statistic] >= threshold for row in subset),
                }
        result[name] = {
            "inclusive_development_threshold": threshold,
            "groups": groups,
            "scope": (
                "constructed smoke controls reported after threshold selection; not RF specificity"
            ),
        }
    return result


def run() -> dict:
    signal.alarm(300)
    design = json.loads((HERE / "design.json").read_text())
    dataset_payload = load_json(DATASET / "cases.json", design["dataset_cases_sha256"])
    reference_payload = load_json(REFERENCE, design["reference_results_sha256"])
    control_payload = load_json(CONTROL_DATASET / "cases.json", design["control_cases_sha256"])
    reference = load_reference(reference_payload)
    development = select_cases(dataset_payload, "dev")
    controls = select_cases(control_payload, "control", controls=True)
    library = ensure_rank_library(design)
    sparse_library = ensure_sparse_library()
    repetitions = design["timing"]["repetitions"]
    warmups = design["timing"]["warmups_per_geometry"]
    rows = []
    control_rows = []
    with ExitStack() as stack:
        workspaces = {
            (rate, edge): stack.enter_context(NativeWindowRank(library, rate, edge, 512))
            for rate in RATES
            for edge in ("lower", "upper")
        }
        sparse_workspaces = {rate: SparseScout(sparse_library, rate) for rate in RATES}
        for workspace in workspaces.values():
            zeros = np.zeros((workspace.rate * 120 // 1000, 2), dtype="<i2")
            for _ in range(warmups):
                workspace.run(zeros)

        def process(case: dict, root: Path, *, is_control: bool) -> None:
            iq = load_iq(root, case)
            workspace = workspaces[(case["rate_hz"], case["edge"])]
            sparse_workspace = sparse_workspaces[case["rate_hz"]]
            for rx in range(2):
                receiver_hash = array_digest(np.ascontiguousarray(iq[:, rx, :]))
                rank_results = []
                sparse_results = []
                rank_timings = []
                sparse_timings = []
                for repetition in range(repetitions):
                    order = ("rank", "sparse")
                    if repetition % 2:
                        order = tuple(reversed(order))
                    for primitive in order:
                        cpu_start = time.thread_time_ns()
                        wall_start = time.perf_counter_ns()
                        values = np.ascontiguousarray(iq[:, rx, :])
                        if primitive == "rank":
                            result = workspace.run(values)
                            rank_timings.append(
                                {
                                    "cpu_ms": (time.thread_time_ns() - cpu_start) / 1e6,
                                    "wall_ms": (time.perf_counter_ns() - wall_start) / 1e6,
                                    "native_cpu_ms": float(result.total_cpu_ms),
                                    "native_wall_ms": float(result.total_wall_ms),
                                }
                            )
                            rank_results.append(screen_statistics(result))
                        else:
                            result = sparse_workspace.run(values)
                            sparse_timings.append(
                                {
                                    "cpu_ms": (time.thread_time_ns() - cpu_start) / 1e6,
                                    "wall_ms": (time.perf_counter_ns() - wall_start) / 1e6,
                                    "native_cpu_ms": float(result.cpu_ms),
                                    "native_wall_ms": float(result.wall_ms),
                                }
                            )
                            sparse_results.append(
                                (
                                    float(result.power_sum_score),
                                    tuple(float(value) for value in result.window_scores),
                                    int(result.pairs_per_window),
                                )
                            )
                if any(result != rank_results[0] for result in rank_results[1:]):
                    raise ValueError("native rank changed across repetitions")
                if any(result != sparse_results[0] for result in sparse_results[1:]):
                    raise ValueError("sparse scout changed across repetitions")
                if array_digest(np.ascontiguousarray(iq[:, rx, :])) != receiver_hash:
                    raise ValueError("receiver input changed across repetitions")
                score_max, score_contrast = rank_results[0]
                sparse_power, sparse_windows, sparse_pairs = sparse_results[0]
                row = {
                    "case_id": case["case_id"],
                    "rx": rx,
                    "rate_hz": case["rate_hz"],
                    "edge": case["edge"],
                    "channel": case["channel"],
                    "session_id": case.get("session_id"),
                    "visit_index": case.get("visit_index"),
                    "source_start_counter": case.get("source_start_counter"),
                    "input_sha256": receiver_hash,
                    "score_max": score_max,
                    "score_contrast": score_contrast,
                    "sparse_power": sparse_power,
                    "sparse_window_scores": sparse_windows,
                    "sparse_pairs_per_window": sparse_pairs,
                    "rank_cpu_ms": statistics.median(item["cpu_ms"] for item in rank_timings),
                    "rank_wall_ms": statistics.median(item["wall_ms"] for item in rank_timings),
                    "sparse_cpu_ms": statistics.median(item["cpu_ms"] for item in sparse_timings),
                    "sparse_wall_ms": statistics.median(item["wall_ms"] for item in sparse_timings),
                    "rank_timings": rank_timings,
                    "sparse_timings": sparse_timings,
                }
                if is_control:
                    row.update(
                        truth_kind=case["truth"]["kind"],
                        starlink_model_present=case["truth"]["starlink_model_present"],
                    )
                    control_rows.append(row)
                    continue
                key = (case["case_id"], rx)
                reference_row = reference[key]
                if (
                    reference_row["start_counter"] != case["source_start_counter"]
                    or reference_row["end_counter"] != case["source_end_counter_exclusive"]
                    or reference_row["rate_hz"] != case["rate_hz"]
                ):
                    raise ValueError(f"source-counter association mismatch: {key}")
                row.update(
                    reference_positive=reference_row["reference_positive"],
                    baseline_cpu_ms=statistics.median(
                        value["cpu_ms"] for value in reference_row["baseline_times"]
                    ),
                )
                rows.append(row)

        for case in development:
            process(case, DATASET, is_control=False)
        if len(rows) != 256 or sum(row["reference_positive"] for row in rows) != 36:
            raise ValueError("development result association failed")
        thresholds = {
            "rank_max_score": threshold_for_full_retention(rows, "score_max"),
            "sparse_lag3_power": threshold_for_full_retention(rows, "sparse_power"),
        }
        for case in controls:
            process(case, CONTROL_DATASET, is_control=True)

    summaries = {
        "rank_max_score": summarize_variant(
            rows, "score_max", thresholds["rank_max_score"], "rank_cpu_ms"
        ),
        "sparse_lag3_power": summarize_variant(
            rows, "sparse_power", thresholds["sparse_lag3_power"], "sparse_cpu_ms"
        ),
    }
    return {
        "schema": "org.leo.research.ds5-cached-scout-results.v1",
        "status": "development_reference_relative_screening_not_physical_absence",
        "design_sha256": digest(HERE / "design.json"),
        "runner_sha256": digest(Path(__file__)),
        "dataset_cases_sha256": digest(DATASET / "cases.json"),
        "reference_results_sha256": digest(REFERENCE),
        "control_cases_sha256": digest(CONTROL_DATASET / "cases.json"),
        "native_binary_sha256": digest(library),
        "native_profile_sha256": digest(NATIVE_PROFILE),
        "sparse_binary_sha256": digest(sparse_library),
        "sparse_source_sha256": digest(HERE / "sparse_lag.c"),
        "host": platform.uname()._asdict(),
        "rows": rows,
        "control_rows": control_rows,
        "summary": summaries,
        "control_summary": summarize_controls(control_rows, thresholds),
        "limitations": [
            "thresholds are development reference-relative and do not label nonroutes "
            "as noise or absence",
            "5 MS/s threshold transfer is unverified because development has zero "
            "reference positives",
            "synthetic controls are smoke cases and were not used to select thresholds",
            "server timing is not ARM timing; file loading and hash verification are excluded",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "results.json")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(HERE) or output.exists():
        raise ValueError("new output must be beneath scout and must not already exist")
    result = run()
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"summary": result["summary"], "controls": result["control_summary"]}))


if __name__ == "__main__":
    main()
