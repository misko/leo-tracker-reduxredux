"""Attribute original acquisition work and batch validation of the sealed index."""

from contextlib import contextmanager
from functools import cache
from inspect import getsource
from textwrap import dedent
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import Json, TypeAdapter

from .signed_ingress_reuse import measured_ingress


def line_rows(payload, model):
    return [model.model_validate_json(line) for line in payload.splitlines()]


@cache
def index_adapter(model):
    return TypeAdapter(list[Json[model]])


def batch_rows(payload, model):
    # Json[model] parses each element in JSON mode. No delimiter or outer array
    # is inserted among independently authenticated input documents.
    try:
        return index_adapter(model).validate_python(payload.splitlines())
    except ValueError:
        return line_rows(payload, model)


def bind_index_parser(release, parse):
    original = 'rows = [index_type.model_validate_json(line) for line in index_bytes.splitlines()]'
    source = dedent(getsource(release))
    if source.count(original) != 1 or parse.__name__ in release.__globals__:
        raise ValueError("Installed index parser binding changed")
    globals_ = release.__globals__ | {parse.__name__: parse}
    exec(compile(source.replace(original, f'rows = {parse.__name__}(index_bytes, index_type)'),
                 release.__code__.co_filename, 'exec'), globals_)
    return globals_[release.__name__]


@contextmanager
def attributed_ingress(buffer, costs, parse):
    from leo.storage.short_window import ShortWindowReader
    from tools import algo08_scan

    before = ShortWindowReader.windows
    stock_support = algo08_scan.valid_window_support
    stock_loads = algo08_scan.json.loads
    stock_canonical = algo08_scan.canonical_digest

    def timed_index_parse(payload, model):
        return costs.time("index_model", parse, payload, model)

    def canonical(items):
        stage = "detection_authority" if items[0] == "cancellation" else "iq_authority"
        return costs.time(stage, stock_canonical, items)

    def support(*args):
        return costs.time("support_gate", stock_support, *args)

    def retune(*args):
        return costs.time("retune_json", stock_loads, *args)

    with measured_ingress(buffer, costs):
        windows = bind_index_parser(before, timed_index_parse)
        with (patch.object(ShortWindowReader, "windows", windows),
              patch.object(algo08_scan, "canonical_digest", canonical),
              patch.object(algo08_scan, "valid_window_support", support),
              patch.object(algo08_scan, "json", SimpleNamespace(loads=retune))):
            yield


def breakdown(row):
    spans = row["work"]["cpu_ns"]
    callback = row["callback_cpu_ns"]
    native = sum(row["native"]["native_cpu_ns"].values())
    stages = dict(spans, native=native, other_callback=callback-native)
    stages["compressed_verified"] -= stages["compressed_descriptor"]
    stages["residual"] = row["acquire_cpu_ns"] - sum(stages.values())
    if min(stages.values()) < 0:
        raise ValueError("Stage clocks overlap or exceed acquisition")
    return stages
