"""Resume one source-sealed progressive replay after an external SIGTERM."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import platform
import resource
import signal
import sys
import time
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import TypeAdapter

from leo.scanner.models import ScannerConfiguration, ScanTarget

HERE = Path(__file__).resolve().parent
ORIGINAL_RUN_PATH = HERE / "run.py"
BASE = HERE.parent / "2026_09_28_ds7_glrt_benchmark"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_original_run():
    spec = importlib.util.spec_from_file_location("ds7_progressive_original_run", ORIGINAL_RUN_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load frozen progressive runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


original_run = _load_original_run()
METHODS = tuple(original_run.METHODS)


class ReplayDeadline(BaseException):
    """Escape per-call error handling and still write a terminal receipt."""


def terminate(signum: int, _frame: object) -> None:
    name = signal.Signals(signum).name
    raise ReplayDeadline(f"composite replay terminated by {name}")


def _expected_entries(
    contexts: Sequence[Mapping[str, Any]],
) -> Iterator[tuple[int, int, Mapping[str, Any], str]]:
    for repeat in range(2):
        for ordinal, context in enumerate(contexts):
            shift = (ordinal + repeat) % len(METHODS)
            for method in METHODS[shift:] + METHODS[:shift]:
                yield repeat, ordinal, context, method


def _finite_timing(row: Mapping[str, Any]) -> None:
    timing = row.get("timing")
    if not isinstance(timing, Mapping):
        raise ValueError("partial row lacks timing")
    for name in ("cpu_s", "wall_s"):
        value = timing.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"partial row timing {name} is not numeric")
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"partial row timing {name} is invalid")


def _validate_partial_rows(
    rows: Sequence[Mapping[str, Any]],
    contexts: Sequence[Mapping[str, Any]],
) -> list[tuple[int, int, Mapping[str, Any], str]]:
    expected = list(_expected_entries(contexts))
    if len(rows) >= len(expected):
        raise ValueError("predecessor must be a nonempty incomplete prefix")
    seen: set[tuple[int, int, str]] = set()
    for index, row in enumerate(rows):
        repeat, ordinal, context, method = expected[index]
        if row.get("status") != "ok":
            raise ValueError(f"partial row {index} is not successful")
        if row.get("repeat") != repeat or row.get("method") != method:
            raise ValueError(f"partial row {index} violates rotated method order")
        if row.get("context") != context:
            raise ValueError(f"partial row {index} context differs from frozen input")
        key = (repeat, ordinal, method)
        if key in seen:
            raise ValueError(f"partial row {index} duplicates a call key")
        seen.add(key)
        if not isinstance(row.get("result"), Mapping):
            raise ValueError(f"partial row {index} lacks a result")
        if not isinstance(row.get("diagnostics"), Mapping):
            raise ValueError(f"partial row {index} lacks diagnostics")
        _finite_timing(row)
    return expected[len(rows) :]


def _validate_predecessor(
    prior: Path,
    inputs_path: Path,
    plan_path: Path,
    contexts: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[tuple[int, int, Mapping[str, Any], str]]]:
    receipt_path = prior / "run.json"
    rows_path = prior / "rows.jsonl"
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("schema") != "ds7-glrt-run/v1":
        raise ValueError("predecessor schema differs")
    if receipt.get("complete") is not False or receipt.get("sources_unchanged") is not False:
        raise ValueError("predecessor is not the expected incomplete attempt")
    if receipt.get("failed_calls") != 0:
        raise ValueError("predecessor records failed calls")
    if receipt.get("methods") != list(METHODS) or receipt.get("repetitions") != 2:
        raise ValueError("predecessor method schedule differs")
    planned = len(contexts) * len(METHODS) * 2
    if receipt.get("planned_calls") != planned:
        raise ValueError("predecessor planned call count differs")
    if receipt.get("plan_sha256") != sha(plan_path):
        raise ValueError("predecessor plan hash differs")
    if receipt.get("input_manifest_sha256") != sha(inputs_path):
        raise ValueError("predecessor input manifest hash differs")
    source_hashes = receipt.get("source_hashes")
    if not isinstance(source_hashes, Mapping) or not source_hashes:
        raise ValueError("predecessor lacks source hashes")
    for source, expected_hash in source_hashes.items():
        path = Path(source)
        if not path.is_file() or sha(path) != expected_hash:
            raise ValueError(f"predecessor source changed: {source}")
    lines = rows_path.read_text().splitlines()
    if not lines:
        raise ValueError("predecessor has no completed rows")
    rows = [json.loads(line) for line in lines]
    missing = _validate_partial_rows(rows, contexts)
    return receipt, rows, missing


def _configuration(iq: np.ndarray, context: Mapping[str, Any]) -> ScannerConfiguration:
    rate = context["rate_hz"]
    duration = iq.shape[0] * 1_000 / rate
    if duration != int(duration):
        raise ValueError("nonintegral dwell")
    return ScannerConfiguration(
        sample_rate_hz=rate,
        bandwidth_hz=rate,
        dwell_ms=int(duration),
        targets=(ScanTarget.model_validate(context["target"]),),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    plan_path = BASE / "plan.json"
    inputs_path = args.inputs / "inputs.json"
    plan = json.loads(plan_path.read_text())
    inputs = json.loads(inputs_path.read_text())
    original_run.validate_inputs(plan, inputs, plan_path)
    contexts = inputs["rows"]
    prior_receipt_sha = sha(args.prior / "run.json")
    prior_rows_sha = sha(args.prior / "rows.jsonl")
    prior_receipt, prior_rows, missing = _validate_predecessor(
        args.prior,
        inputs_path,
        plan_path,
        contexts,
    )
    if len(prior_rows) != 526 or len(missing) != 34:
        raise ValueError("resume is bound to the 526-row SIGTERM predecessor")

    from methods_sparse import make_method

    dependencies = {
        str(Path(path)): digest
        for path, digest in prior_receipt["source_hashes"].items()
    }
    dependencies[str(Path(__file__))] = sha(Path(__file__))
    args.output.mkdir(parents=True, exist_ok=False)
    os.sched_setaffinity(0, {0})
    header: dict[str, Any] = {
        "schema": "ds7-glrt-run/v1",
        "complete": False,
        "sources_unchanged": False,
        "methods": list(METHODS),
        "repetitions": 2,
        "planned_calls": len(contexts) * len(METHODS) * 2,
        "plan_sha256": sha(plan_path),
        "input_manifest_sha256": sha(inputs_path),
        "dataset_sha256": plan["dataset_sha256"],
        "source_hashes": dependencies,
        "python": sys.version,
        "numpy": np.__version__,
        "platform": platform.platform(),
        "affinity": sorted(os.sched_getaffinity(0)),
        "threads": {
            key: os.environ.get(key) for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS")
        },
        "scope": (
            "composite resident-CI16 replay; immutable predecessor rows plus cold-process "
            "execution of only missing calls; no RF"
        ),
        "failed_calls": 0,
        "calls": len(prior_rows),
        "composite": True,
        "predecessor": {
            "directory": str(args.prior),
            "receipt_sha256": prior_receipt_sha,
            "rows_sha256": prior_rows_sha,
            "copied_rows": len(prior_rows),
            "complete": False,
            "reported_exit_status": 143,
            "reported_signal": "SIGTERM",
            "restart": "fresh process and fresh method objects; cold caches",
        },
        "resumed_calls": 0,
    }
    receipt_path = args.output / "run.json"
    rows_path = args.output / "rows.jsonl"
    receipt_path.write_text(json.dumps(header, indent=2) + "\n")
    prior_bytes = (args.prior / "rows.jsonl").read_bytes()
    if prior_bytes and not prior_bytes.endswith(b"\n"):
        raise ValueError("predecessor rows are not newline terminated")
    rows_path.write_bytes(prior_bytes)

    workers = {
        name: original_run.make_baseline(name)
        if name in ("original", "optimized")
        else make_method(name)
        for name in METHODS
    }
    signal.signal(signal.SIGALRM, terminate)
    signal.signal(signal.SIGTERM, terminate)
    signal.alarm(600)
    started = time.monotonic()
    current_key: tuple[int, int] | None = None
    iq: np.ndarray | None = None
    config: ScannerConfiguration | None = None
    try:
        with rows_path.open("a") as output:
            for repeat, ordinal, context, name in missing:
                key = (repeat, ordinal)
                if key != current_key:
                    path = args.inputs / context["file"]
                    if (
                        path.parent.resolve() != args.inputs.resolve()
                        or sha(path) != context["sha256"]
                    ):
                        raise ValueError("input payload binding")
                    iq = np.load(path, allow_pickle=False)
                    if list(iq.shape) != context["shape"] or str(iq.dtype) != context["dtype"]:
                        raise ValueError("input geometry")
                    config = _configuration(iq, context)
                    current_key = key
                assert iq is not None and config is not None
                cpu = time.process_time()
                wall = time.perf_counter()
                try:
                    samples = np.empty(iq.shape[:2], dtype=np.complex64)
                    samples.real = iq[:, :, 0]
                    samples.imag = iq[:, :, 1]
                    got = workers[name].analyze(samples, config, context["target"]["edge"], context)
                    timing = {
                        "cpu_s": time.process_time() - cpu,
                        "wall_s": time.perf_counter() - wall,
                    }
                    result = TypeAdapter(type(got.analysis)).dump_python(got.analysis, mode="json")
                    row = {
                        "context": context,
                        "method": name,
                        "repeat": repeat,
                        "status": "ok",
                        "result": result,
                        "diagnostics": got.diagnostics,
                        "timing": timing,
                    }
                except Exception as error:
                    row = {
                        "context": context,
                        "method": name,
                        "repeat": repeat,
                        "status": "failed",
                        "result": None,
                        "diagnostics": {"error": repr(error)},
                        "timing": {
                            "cpu_s": time.process_time() - cpu,
                            "wall_s": time.perf_counter() - wall,
                        },
                    }
                    header["failed_calls"] += 1
                output.write(json.dumps(row, allow_nan=False) + "\n")
                output.flush()
                header["calls"] += 1
                header["resumed_calls"] += 1
                print(
                    json.dumps(
                        {
                            "repeat": repeat,
                            "rate": context["rate_hz"],
                            "visit": context["visit_index"],
                            "method": name,
                            "calls": header["calls"],
                            "failures": header["failed_calls"],
                        }
                    ),
                    flush=True,
                )
        predecessor_unchanged = (
            sha(args.prior / "run.json") == prior_receipt_sha
            and sha(args.prior / "rows.jsonl") == prior_rows_sha
        )
        header["sources_unchanged"] = (
            predecessor_unchanged
            and all(
                Path(path).is_file() and sha(Path(path)) == digest
                for path, digest in dependencies.items()
            )
        )
        header["complete"] = (
            header["calls"] == header["planned_calls"]
            and header["resumed_calls"] == len(missing)
            and not header["failed_calls"]
            and header["sources_unchanged"]
        )
        if not header["complete"]:
            raise RuntimeError("composite replay is incomplete, failed, or source-changed")
    except BaseException as error:
        header["error"] = repr(error)
        header["terminal"] = True
        raise
    finally:
        signal.alarm(0)
        header["wall_s"] = time.monotonic() - started
        header["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        receipt_path.write_text(json.dumps(header, indent=2) + "\n")


if __name__ == "__main__":
    main()
