"""Measure cyclic collector work in a dedicated saved-solver worker."""

from contextlib import ExitStack, contextmanager
from functools import wraps
import gc
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from leo.analysis.localization_v3 import (
    conservative_recovery, family_cavity, history_policy, signed_context,
)
from tools import algo08_position
from tools.pipeline_eval.variants import algo08_causal_reuse, v5_core
from tools.pipeline_eval.variants.experimental.preparation_gc import defer_collection


PHASES = (
    "solver_other", "prepare_scan", "parse_catalogue", "preparation_collection",
    "serialize_preparation", "scan_context", "initial", "conservative", "salvage", "family",
    "signed", "cavity_nominate", "cavity_fit", "selected_packet", "closing_collection",
)


def generation_counts():
    return dict(calls=0, cpu_ns=0, wall_ns=0, collected=0, uncollectable=0)


class CollectorAudit:
    def __init__(self):
        self.phase = "solver_other"
        self.begun = None
        self.collections = {name: [generation_counts() for _ in range(3)] for name in PHASES}
        self.phases = {name: dict(calls=0, cpu_ns=0) for name in PHASES}

    def observe(self, action, info):
        if action == "start":
            self.begun = self.phase, perf_counter_ns(), process_time_ns()
        elif action == "stop" and self.begun is not None:
            cpu, wall = process_time_ns(), perf_counter_ns()
            phase, started_wall, started_cpu = self.begun
            self.begun = None
            row = self.collections[phase][info["generation"]]
            row["calls"] += 1
            row["cpu_ns"] += cpu - started_cpu
            row["wall_ns"] += wall - started_wall
            row["collected"] += info["collected"]
            row["uncollectable"] += info["uncollectable"]

    @contextmanager
    def scope(self, name):
        previous, self.phase = self.phase, name
        started = process_time_ns()
        try:
            yield
        finally:
            self.phase = previous
            row = self.phases[name]
            row["calls"] += 1
            row["cpu_ns"] += process_time_ns() - started

    def wrap(self, name, original):
        @wraps(original)
        def measured(*args, **kwargs):
            with self.scope(name):
                return original(*args, **kwargs)

        return measured


@contextmanager
def measure_collector(*, defer_preparation=False):
    audit = CollectorAudit()
    callback = audit.observe
    bindings = (
        (algo08_position, "prepare_native_scan", "prepare_scan"),
        (algo08_causal_reuse.CausalPreparationParser, "__call__", "parse_catalogue"),
        (algo08_position, "_prepared_values", "serialize_preparation"),
        (v5_core, "scan_context", "scan_context"),
        (v5_core, "initial_selection", "initial"),
        (conservative_recovery, "conservative_recovery", "conservative"),
        (conservative_recovery, "salvage", "salvage"),
        (history_policy, "history_policy", "family"),
        (signed_context, "signed_context", "signed"),
        (family_cavity, "nominate_families", "cavity_nominate"),
        (family_cavity, "cavity_policy", "cavity_fit"),
        (algo08_position, "selected_packet", "selected_packet"),
    )
    with ExitStack() as stack:
        for owner, name, phase in bindings:
            operation = getattr(owner, name)
            if phase == "prepare_scan" and defer_preparation:
                collect = audit.wrap("preparation_collection", gc.collect)
                operation = defer_collection(operation, collect=collect)
            stack.enter_context(patch.object(owner, name, audit.wrap(phase, operation)))
        gc.callbacks.append(callback)
        stack.callback(gc.callbacks.remove, callback)
        yield audit
