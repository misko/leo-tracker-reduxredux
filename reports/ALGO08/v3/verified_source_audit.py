"""Disjoint source, compiler, import and adapter setup timings."""

import ast
import builtins
from collections import Counter, defaultdict
from contextlib import _GeneratorContextManager, contextmanager
import __future__
import hashlib
import importlib._bootstrap as imports
from importlib.machinery import SourceFileLoader
import inspect
from pathlib import Path
import sys
from time import perf_counter_ns, process_time_ns
from types import CodeType
from unittest.mock import patch


SOURCE_ROOT = "/opt/leo-algo08/"
RAW_SHA = hashlib.sha256
FUTURE_FLAGS = sum(getattr(__future__, name).compiler_flag for name in __future__.all_feature_names)
ADAPTERS = frozenset(("exact_ports", "exact_grid", "cached_predictive_grid", "named_solve",
                      "measured_curved_design", "grid_handoff", "bound_exterior_veto", "elected_elements",
                      "stable_recovery", "corner_support", "graph_execution", "gate_binding",
                      "successor_binding", "routed_binding", "risk_solve", "measured_readout"))


def now():
    return process_time_ns(), perf_counter_ns()


def attr(frame):
    code = frame.f_code
    return f"{code.co_filename}:{frame.f_lineno}:{code.co_name}"


class SourceAudit:
    def __init__(self, project):
        self.project = str(project) + "/"
        self.phase = "startup"
        self.events, self.stack = [], []
        self.original_bytes, self.inspected_bytes = {}, {}
        self.seen = Counter()
        self.loader_depth = 0

    def source_path(self, file):
        name = str(file)
        return (name.startswith((SOURCE_ROOT, self.project))
                and (name.endswith((".py", ".c", ".h")) or name == "/opt/leo-algo08/algo08v3/run"))

    @contextmanager
    def span(self, kind, label, caller):
        parent = self.stack[-1] if self.stack else None
        row = dict(kind=kind, slot=len(self.events), phase=self.phase, label=str(label), caller=caller,
                   nested_cpu_ns=0, nested_wall_ns=0)
        self.events.append(row)
        self.stack.append(row)
        begin_cpu, begin_wall = now()
        try:
            yield row
        finally:
            cpu, wall = now()
            row.update(cpu_ns=cpu - begin_cpu, wall_ns=wall - begin_wall)
            row.update(exclusive_cpu_ns=max(0, row["cpu_ns"] - row["nested_cpu_ns"]),
                       exclusive_wall_ns=max(0, row["wall_ns"] - row["nested_wall_ns"]))
            if parent is not None:
                parent["nested_cpu_ns"] += row["cpu_ns"]
                parent["nested_wall_ns"] += row["wall_ns"]
            self.stack.pop()

    def repeat(self, row, token):
        key = row["kind"], row["label"], token
        row["repeat"] = self.seen[key] > 0
        self.seen[key] += 1

    @contextmanager
    def bind(self):
        read, text = Path.read_bytes, Path.read_text
        getsource, compile_source = inspect.getsource, builtins.compile
        load, source_to_code = imports._find_and_load, SourceFileLoader.source_to_code
        cm_enter, cm_exit = _GeneratorContextManager.__enter__, _GeneratorContextManager.__exit__

        def file_read(operation, path, *args, **kwargs):
            if not self.source_path(path):
                return operation(path, *args, **kwargs)
            with self.span("source_read", path, attr(sys._getframe(2))) as row:
                note = operation(path, *args, **kwargs)
            blob = note if type(note) is bytes else note.encode()
            pin = RAW_SHA(blob).hexdigest()
            self.original_bytes[id(blob)] = blob, str(path), pin
            row.update(bytes=len(blob), source_sha256=pin)
            self.repeat(row, pin)
            return note

        def sha256(data=b"", *args, **kwargs):
            admitted = self.original_bytes.get(id(data))
            if admitted is None and type(data) is bytes and 0 < len(data) <= 200_000:
                admitted = self.inspected_bytes.get(data)
            if admitted is None:
                return RAW_SHA(data, *args, **kwargs)
            _, path, pin = admitted
            with self.span("source_sha256", path, attr(sys._getframe(1))) as row:
                result = RAW_SHA(data, *args, **kwargs)
            self.repeat(row, pin)
            return result

        def source(operation):
            actual = inspect.unwrap(operation)
            code = getattr(actual, "__code__", actual)
            if type(code) is not CodeType or not self.source_path(code.co_filename):
                return getsource(operation)
            with self.span("inspect_source", f"{code.co_filename}:{code.co_firstlineno}:{code.co_name}",
                           attr(sys._getframe(1))) as row:
                result = getsource(operation)
            blob = result.encode()
            pin = RAW_SHA(blob).hexdigest()
            self.inspected_bytes[blob] = blob, row["label"], pin
            row.update(bytes=len(blob), source_sha256=pin)
            self.repeat(row, (id(code), id(getattr(actual, "__globals__", None)), id(actual), pin))
            return result

        def build(value, filename, mode, flags=0, dont_inherit=False, optimize=-1, *, _feature_version=-1):
            origin = sys._getframe(1)
            if not dont_inherit:
                flags |= origin.f_code.co_flags & FUTURE_FLAGS

            def ordinary():
                return compile_source(value, filename, mode, flags, True, optimize, _feature_version=_feature_version)

            if not self.source_path(filename):
                return ordinary()
            kind = "loader_compile" if self.loader_depth else "explicit_compile"
            with self.span(kind, filename, attr(origin)) as row:
                result = ordinary()
            if type(value) is str or type(value) is bytes:
                blob = value.encode() if type(value) is str else value
            elif isinstance(value, ast.AST):
                blob = ast.dump(value, include_attributes=True).encode()
            else:
                return result
            pin = RAW_SHA(blob).hexdigest()
            row.update(bytes=len(blob), compile_mode=mode, ast_input=isinstance(value, ast.AST), source_sha256=pin)
            # Code-call ownership includes current globals and inherited flags.
            self.repeat(row, (pin, mode, flags, optimize, _feature_version, id(origin.f_globals)))
            return result

        def loader(self_, *args, **kwargs):
            self.loader_depth += 1
            try:
                return source_to_code(self_, *args, **kwargs)
            finally:
                self.loader_depth -= 1

        def first_import(name, mechanism):
            if name in sys.modules:
                return load(name, mechanism)
            with self.span("module_import", name, attr(sys._getframe(1))):
                return load(name, mechanism)

        def adapter(operation, label, instance, *args):
            generator = getattr(instance, "gen", None)
            code = getattr(generator, "gi_code", None)
            if code is None or code.co_name not in ADAPTERS or not self.source_path(code.co_filename):
                return operation(instance, *args)
            with self.span(label, f"{code.co_filename}:{code.co_firstlineno}:{code.co_name}", attr(sys._getframe(2))):
                return operation(instance, *args)

        with (patch.object(Path, "read_bytes", lambda path: file_read(read, path)),
              patch.object(Path, "read_text", lambda path, *a, **kw: file_read(text, path, *a, **kw)),
              patch.object(hashlib, "sha256", sha256), patch.object(inspect, "getsource", source),
              patch.object(builtins, "compile", build), patch.object(imports, "_find_and_load", first_import),
              patch.object(SourceFileLoader, "source_to_code", loader),
              patch.object(_GeneratorContextManager, "__enter__", lambda cm: adapter(cm_enter, "adapter_enter", cm)),
              patch.object(_GeneratorContextManager, "__exit__", lambda cm, *a: adapter(cm_exit, "adapter_exit", cm, *a))):
            yield


def summarize(events):
    result = defaultdict(lambda: Counter(calls=0, cpu_ns=0, wall_ns=0))
    sites = defaultdict(Counter)
    for row in events:
        group = row["phase"], row["kind"], "repeat" if row.get("repeat") else "other"
        target = result[group]
        site = sites[(*group, row["label"], row["caller"])]
        for value in (target, site):
            value.update(calls=1, cpu_ns=row["exclusive_cpu_ns"], wall_ns=row["exclusive_wall_ns"])
    groups = [dict(phase=phase, kind=kind, scope=state, **counts) for (phase, kind, state), counts in sorted(result.items())]
    repeats = [dict(phase=phase, kind=kind, label=label, caller=caller, **counts)
               for (phase, kind, state, label, caller), counts in sites.items() if state == "repeat"]
    return dict(groups=groups, repeats=sorted(repeats, key=lambda row: row["cpu_ns"], reverse=True))
