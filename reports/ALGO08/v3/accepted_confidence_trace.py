"""Exact operand and clock probes for the original lean confidence calculation."""

from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from hashlib import sha256
from inspect import getsource
import json
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np


PIN = "6692c234ab897ec62057b1472ed25b47392345a84d7fa5730190bbfdd27086b8"
CALLS = {
    "sensitive_rows(scan, node, keep)": 'probe.call("support", sensitive_rows, scan, node, keep)',
    'problem(scan, node, "c0", keep, np.asarray(saved["phase_reference"]))':
        'probe.call("conditional_problem", problem, scan, node, "c0", keep, np.asarray(saved["phase_reference"]))',
    "p.state(point)": "probe.state(p, point)",
    "phase_widths(scan, list(range(len(scan.norads))))": "probe.widths(phase_widths, scan)",
    "scan_kernel.prepare_phase_geometry(scan.sky, times)":
        "probe.prepare(scan_kernel.prepare_phase_geometry, scan, times)",
    "family_weighting.phase_linear_frequency(geometry, *scan.search_region.latlon(anchor))":
        "probe.project(family_weighting.phase_linear_frequency, geometry, scan.search_region.latlon(anchor))",
    "family_weighting.candidate_profile(y, q * f[:, columns], q * derivative[:, columns],":
        "probe.profile(family_weighting.candidate_profile, j, q, columns, y, q * f[:, columns], q * derivative[:, columns],",
    'family_weighting.competitor_confidence(scored["cost"], j)':
        'probe.call("competitor", family_weighting.competitor_confidence, scored["cost"], j)',
}
METRICS = ("cpu_ns", "elapsed_ns")


def now():
    return process_time_ns(), perf_counter_ns()


def elapsed(start):
    return dict(zip(METRICS, (a-b for a,b in zip(now(), start, strict=True)), strict=True))


def fingerprint(*values):
    """Hash dtype, shape and ordered bits, including signed zero and byte order."""
    digest = sha256()

    def tag(value):
        digest.update(json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode())
        digest.update(b"\0")

    def add(value):
        if is_dataclass(value):
            kind = type(value)
            names = [f.name for f in fields(value)]
            tag((kind.__module__, kind.__qualname__, names))
            for name in names:
                add(getattr(value, name))
        elif isinstance(value, (np.ndarray, np.generic, float)):
            array = np.asarray(value)
            if array.dtype.hasobject:
                raise ValueError("Object arrays cannot identify numerical operands")
            tag((array.dtype.str, array.shape))
            digest.update(memoryview(np.ascontiguousarray(array)).cast("B"))
        elif isinstance(value, (tuple, list)):
            tag(len(value))
            for item in value:
                add(item)
        elif value is None or isinstance(value, (str, bool, int)):
            tag(value)
        else:
            raise TypeError(f"Unknown numerical operand {type(value).__qualname__}")

    add(values)
    return digest.hexdigest()


class ConfidenceTrace:
    def __init__(self):
        self.records = []
        self.current = None

    def record(self, operation, *args, **kwargs):
        self.current = {"stages": {}, "projections": [], "profiles": []}
        start = now()
        result = operation(*args, **kwargs)
        self.current["output"] = self.hash(result)
        self.current["inclusive"] = elapsed(start)
        self.records.append(self.current)
        self.current = None
        return result

    def call(self, stage, operation, *args):
        start = now()
        result = operation(*args)
        self.current["stages"].setdefault(stage, []).append(elapsed(start))
        return result

    def hash(self, *values):
        return self.call("fingerprints", fingerprint, *values)

    def state(self, problem, point):
        state = self.call("conditional_state", problem.state, point)
        self.current["nuisance"] = self.hash(problem.keep, problem.reference, point,
                                             state["beta"], state["smooth"])
        return state

    def widths(self, operation, scan):
        result = self.call("causal_widths", operation, scan, list(range(len(scan.norads))))
        self.current["widths"] = self.hash(scan.norads, result[0])
        return result

    def prepare(self, operation, scan, times):
        sky = scan.sky
        self.current["epochs"] = self.hash(scan.origin_utc_ns, times)
        self.current["epoch_count"] = len(times)
        self.current["source_geometry"] = self.hash(
            scan.norads, *(sky[name] for name in ("time_s", "position_km", "velocity_km_s")))
        result = self.call("prepare_projection", operation, sky, times)
        self.current["prepared_geometry"] = self.hash(result)
        return result

    def project(self, operation, grid, coordinate):
        key = self.hash(self.current["prepared_geometry"], tuple(coordinate), 0.0, 11.5e9)
        result = self.call("project", operation, grid, *coordinate)
        self.current["projections"].append(dict(operands=key, output=self.hash(result),
                                                 result_bytes=sum(x.nbytes for x in result)))
        return result

    def profile(self, operation, family, ratio, columns, *args):
        key = self.hash(family, ratio, columns, args)
        result = self.call("profile", operation, *args)
        self.current["profiles"].append(dict(operands=key,
                                              output=self.hash(*(result[name] for name in sorted(result)))))
        return result


@contextmanager
def binding(module, trace):
    path = Path(module.__file__)
    if sha256(path.read_bytes()).hexdigest() != PIN:
        raise ValueError("The original confidence source changed")
    source = getsource(module.minimum_confidence)
    for original, instrumented in CALLS.items():
        if source.count(original) != 1:
            raise ValueError(f"Unexpected original confidence call {original}")
        source = source.replace(original, instrumented)
    code = compile(source, str(path), "exec")

    def observed(*args, **kwargs):
        namespace = dict(vars(module), probe=trace)
        exec(code, namespace)
        return trace.record(namespace["minimum_confidence"], *args, **kwargs)

    with patch.object(module, "minimum_confidence", observed):
        yield


def summarize(records):
    by_stage = {name: [sample for row in records for sample in row["stages"].get(name, ())]
                for name in sorted({stage for row in records for stage in row["stages"]})}
    totals = {name: {metric: sum(x[metric] for x in clocks) for metric in METRICS} | {"calls": len(clocks)}
              for name, clocks in by_stage.items()}
    complete = {metric: sum(row["inclusive"][metric] for row in records) for metric in METRICS}
    residual = {metric: complete[metric]-sum(b[metric] for b in totals.values()) for metric in METRICS}
    if min(residual.values()) < 0:
        raise ValueError("Primitive clocks must be disjoint children of confident evaluation")
    repeats = {}
    for name, stage in (("projections", "project"), ("profiles", "profile")):
        seen, exact = {}, []
        for call, row in enumerate(records):
            for index, item in enumerate(row[name]):
                key, output = item["operands"], item["output"]
                if key in seen:
                    first = seen[key]
                    exact.append(dict(call=call, index=index, previous_call=first["call"],
                                      previous_index=first["index"], output_identical=output==first["output"],
                                      clocks=row["stages"][stage][index]))
                else:
                    seen[key] = dict(call=call, index=index, output=output)
        repeats[name] = exact
    return dict(complete=complete, stages=totals, remainder=residual, exact_input_repeats=repeats)
