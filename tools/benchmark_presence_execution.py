"""Paired execution-only comparison on hash-checked, already opened saved IQ.

Never opens a radio. Search/decision qualification and live duty are not inferred
from numerical parity or desktop timing. Each library is an explicit artifact.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from tools.evaluate_presence_window_rank import load_dwells
from tools.presence_dwell import NativeDwell, unpack
from tools.qualify_native_presence import digest, write_json


def numerical(value):
    """Execution timing is not detector evidence; retain every other field."""
    if isinstance(value, dict):
        return {k: numerical(v) for k, v in value.items() if not k.endswith("_ms")}
    if isinstance(value, list):
        return [numerical(v) for v in value]
    return value


def differences(expected, actual, path="result"):
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or expected.keys() != actual.keys():
            return [path]
        return [p for k in expected for p in differences(expected[k], actual[k], f"{path}.{k}")]
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            return [path]
        return [
            p
            for i, (a, b) in enumerate(zip(expected, actual, strict=True))
            for p in differences(a, b, f"{path}[{i}]")
        ]
    if isinstance(expected, float):
        return [] if math.isclose(expected, actual, rel_tol=1e-9, abs_tol=1e-10) else [path]
    return [] if expected == actual else [path]


def benchmark(source: Path, output: Path, libraries: dict[str, Path], repeats: int):
    if not 2 <= len(libraries) <= 4 or not 1 <= repeats <= 20:
        raise ValueError("two to four variants and one to twenty repetitions required")
    source, output = source.resolve(), output.resolve()
    if any(output.is_relative_to(p) for p in (source, Path("/mnt/qnap01"), Path("/srv/bulk/leo"))):
        raise ValueError("output must be separate from source and archive")
    libraries = {name: path.resolve(strict=True) for name, path in libraries.items()}
    identities = {name: digest(path) for name, path in libraries.items()}
    source_identities = {name: digest(source / name) for name in ("inputs.json", "results.json")}
    tool_identity = digest(Path(__file__))
    output.mkdir(parents=True, exist_ok=False)
    write_json(
        output / "freeze.json",
        {
            "scope": "opened development IQ; not detection or duty qualification",
            "source": str(source),
            "source_inputs_sha256": source_identities["inputs.json"],
            "source_results_sha256": source_identities["results.json"],
            "libraries": {
                name: {"path": str(path), "sha256": identities[name]}
                for name, path in libraries.items()
            },
            "repeats": repeats,
            "rx": 1,
            "screen_bins": 512,
            "confirmations": 1,
            "seeded": False,
            "rtol": 1e-9,
            "atol": 1e-10,
            "tool_sha256": tool_identity,
            "order": "alternate forward/reverse variant order by visit and repetition",
        },
    )
    rows, initialization = [], []
    names = list(libraries)
    with ExitStack() as stack:
        workspaces = {}
        for index, (metadata, iq) in enumerate(load_dwells(source)):
            original = digest_bytes(iq.tobytes())
            rate, edge = metadata["rate_hz"], metadata["edge"]
            for name, library in libraries.items():
                key = name, rate, edge
                if key not in workspaces:
                    cpu, wall = time.process_time_ns(), time.perf_counter_ns()
                    workspaces[key] = stack.enter_context(NativeDwell(library, rate, edge, 512))
                    initialization.append(
                        {
                            "variant": name,
                            "rate_hz": rate,
                            "edge": edge,
                            "cpu_ms": (time.process_time_ns() - cpu) / 1e6,
                            "wall_ms": (time.perf_counter_ns() - wall) / 1e6,
                        }
                    )
            reference = None
            for repeat in range(repeats):
                records = {}
                for name in names if (index + repeat) % 2 == 0 else reversed(names):
                    native = workspaces[name, rate, edge]
                    result = unpack(native.run(iq, maximum=1, seeded=False))
                    screens = unpack(native.screens())
                    records[name] = {"result": result, "screens": screens}
                current_reference = numerical(records[names[0]])
                if reference is None:
                    reference = current_reference
                mismatches = {
                    name: differences(reference, numerical(record))
                    for name, record in records.items()
                }
                rows.append(
                    {
                        "source": metadata,
                        "iq_sha256": original,
                        "repeat": repeat,
                        "variants": records,
                        "mismatches": mismatches,
                    }
                )
            if digest_bytes(iq.tobytes()) != original:
                raise RuntimeError("execution mutated original saved IQ")
            if (index + 1) % 16 == 0:
                print(f"Compared {index + 1} hash-checked dwells", flush=True)
    if identities != {name: digest(path) for name, path in libraries.items()}:
        raise RuntimeError("library identity changed during execution")
    if source_identities != {name: digest(source / name) for name in source_identities}:
        raise RuntimeError("source inventory changed during execution")
    if tool_identity != digest(Path(__file__)):
        raise RuntimeError("benchmark source changed during execution")
    write_json(output / "results.json", rows)
    summary = {
        "initialization": initialization,
        "comparisons": len(rows) * len(names),
        "paired_variant_comparisons": len(rows) * (len(names) - 1),
        "mismatched_comparisons": sum(bool(p) for r in rows for p in r["mismatches"].values()),
        "bit_identical_comparisons": sum(
            numerical(r["variants"][name]) == numerical(r["variants"][names[0]])
            for r in rows
            for name in names
        ),
        "timing": {},
    }
    for rate in sorted({r["source"]["rate_hz"] for r in rows}):
        summary["timing"][str(rate)] = {}
        for name in names:
            subset = [r["variants"][name]["result"] for r in rows if r["source"]["rate_hz"] == rate]
            summary["timing"][str(rate)][name] = {
                field: np.percentile([r[field] for r in subset], [50, 95, 99, 100]).tolist()
                for field in ("total_cpu_ms", "total_wall_ms")
            }
            stages = summary["timing"][str(rate)][name]["stages_cpu_ms"] = {}
            for field in ("conversion_cpu_ms", "coarse_cpu_ms", "fine_cpu_ms", "fractional_cpu_ms"):
                stages[field] = np.percentile(
                    [r["confirmations"][0][field] for r in subset], [50, 95, 99, 100]
                ).tolist()
            stages["screen_cpu_ms"] = np.percentile(
                [r["rank"]["total_cpu_ms"] for r in subset], [50, 95, 99, 100]
            ).tolist()
    write_json(output / "summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if summary["mismatched_comparisons"]:
        raise RuntimeError("numerical parity failed; all comparisons retained")
    return summary


def digest_bytes(value):
    from hashlib import sha256

    return sha256(value).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--library", action="append", required=True, metavar="NAME=PATH")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    pairs = [spec.split("=", 1) for spec in args.library]
    if any(len(pair) != 2 or not pair[0] or not pair[1] for pair in pairs):
        parser.error("libraries require NAME=PATH")
    libraries = {name: Path(path) for name, path in pairs}
    if len(libraries) != len(pairs):
        parser.error("library names must be unique")
    benchmark(args.source, args.output, libraries, args.repeats)


if __name__ == "__main__":
    main()
