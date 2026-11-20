"""Shorten the lifetimes of complete phase problems in bounded compact v5."""

import ctypes
import gc
import hashlib
import inspect
from contextlib import ExitStack, contextmanager
from functools import wraps
from pathlib import Path
from types import FunctionType
from unittest.mock import patch

from tools.pipeline_eval.variants import v5_bounded_cavity

METHOD = "v5_cavity_lifetime"
SIGNED_SHA = "b556b0b9526fb0b2aa1d0cecfedf25f9b652a12c42441ec9ef0d538ab34db49d"
EVENT_SHA = "3a8c9bde7ddddc115fcb219f8588fd51188ef4081567d8e2fe91df8324418e9f"
FAMILY_SHA = "7a20ac84d4c245df95481d10425def01642cbf4d3f45f1f32b9188a78007b3ae"


def dispose(model):
    """Detach self-referential likelihood closures after the final numerical read."""
    for name in (
        "calculate",
        "curved_calculate",
        "state",
        "conditional_frequency",
        "_fixed_phase_geometry_cache",
    ):
        model.__dict__.pop(name, None)


def overlay(function, digest, changes):
    path = Path(inspect.getsourcefile(function))
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError(f"unrecognized lifetime source for {function.__name__}")
    source = inspect.getsource(function)
    for before, after, occurrences in changes:
        if source.count(before) != occurrences:
            raise ValueError(f"unrecognized lifetime anchor for {function.__name__}")
        source = source.replace(before, after)
    namespace = {}
    exec(compile(source, str(path), "exec"), namespace)
    # Keep the real globals so the existing causal-width patch still applies.
    rebuilt = namespace[function.__name__]
    result = FunctionType(
        rebuilt.__code__,
        function.__globals__,
        function.__name__,
        function.__defaults__,
        function.__closure__,
    )
    result.__kwdefaults__ = function.__kwdefaults__
    return result


@contextmanager
def lifetime(sample, *, direct=True):
    from leo.analysis.localization_v3 import event_position, family_cavity, signed_context

    trim = ctypes.CDLL("libc.so.6").malloc_trim
    trim.argtypes = [ctypes.c_size_t]
    trim.restype = ctypes.c_int
    signed = signed_context.signed_context
    cavity = family_cavity.cavity_policy
    if direct:
        signed = overlay(
            signed,
            SIGNED_SHA,
            (
                (
                    "    base = problem(scan, node, 'c0', keep)\n",
                    "    labels = problem(scan, node, 'c0', keep).labels\n",
                    1,
                ),
                ("phase_widths(scan, base.labels)", "phase_widths(scan, labels)", 2),
            ),
        )
        refit = overlay(
            event_position.refit,
            EVENT_SHA,
            (
                (
                    "        reference = phase\n",
                    "        reference = phase\n"
                    "        if _epoch < 4:\n            _lifetime_dispose(p)\n            del p\n",
                    1,
                ),
                ("    return record\n", "    _lifetime_dispose(p)\n    return record\n", 1),
            ),
        )
        path = Path(family_cavity.__file__)
        if hashlib.sha256(path.read_bytes()).hexdigest() != FAMILY_SHA:
            raise ValueError("unrecognized nomination and restoration contract")

    def reclaim(stage):
        sample(stage, "before_gc")
        collected = gc.collect()
        sample(stage, "after_gc", collected=collected)
        returned = trim(0)
        sample(stage, "after_trim", trim_returned=returned)

    @wraps(signed)
    def signed_stage(*args, **kwargs):
        reclaim("signed_context")
        result = signed(*args, **kwargs)
        sample("signed_context", "return")
        reclaim("signed_context_exit")
        return result

    @wraps(cavity)
    def cavity_stage(context, nominations):
        if direct:
            sample("cavity_policy", "before_direct_release")
            dispose(context.pop("base"))
            sample("cavity_policy", "after_direct_release")
        reclaim("cavity_policy")
        result = cavity(context, nominations)
        sample("cavity_policy", "return")
        return result

    with ExitStack() as stack:
        stack.enter_context(patch.object(signed_context, "signed_context", signed_stage))
        stack.enter_context(patch.object(family_cavity, "cavity_policy", cavity_stage))
        if direct:
            stack.enter_context(
                patch.object(event_position, "_lifetime_dispose", dispose, create=True)
            )
            for module in (event_position, signed_context, family_cavity):
                stack.enter_context(patch.object(module, "refit", refit))
        yield


def worker(request, result, library, sample, *, direct=True):
    with lifetime(sample, direct=direct):
        v5_bounded_cavity.worker(request, result, library)
