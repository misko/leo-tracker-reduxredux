from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from named_wide_likelihood import checked_library, inference_scope


def test_changing_the_binary_and_its_manifest_cannot_change_the_operator_pin(tmp_path):
    path = tmp_path / "private_width.so"
    builder = SimpleNamespace(SOURCE_SHA256="approved parent", expanded_source=lambda: "approved C")
    def write(binary, *, source="approved C"):
        path.write_bytes(binary)
        path.with_name("manifest.json").write_text(json.dumps(dict(binary_sha256=sha256(binary).hexdigest(),
            parent_source_sha256=builder.SOURCE_SHA256, source_sha256=sha256(source.encode()).hexdigest())))

    trusted = "sha256:" + sha256(b"trusted binary").hexdigest()
    write(b"trusted binary")
    assert checked_library(path, trusted, builder)[0] == b"trusted binary"
    write(b"different binary")
    with pytest.raises(ValueError, match="operator digest"):
        checked_library(path, trusted, builder)
    write(b"trusted binary", source="another C program")
    with pytest.raises(ValueError, match="source record"):
        checked_library(path, trusted, builder)


def test_widened_binding_limits_retry_to_inference_and_restores_stock_for_selected_packet():
    class Bound:
        def __call__(self):
            return "stock"

    engine, audit = Bound(), {}

    def infer(*, selected_evidence):
        assert engine() == "wider"
        assert selected_evidence() == "stock"
        return engine()

    core = SimpleNamespace(infer=infer)

    @contextmanager
    def widened():
        with patch.object(Bound, "__call__", lambda self: "wider"):
            yield {"calls": 1, "activated": 1}

    with inference_scope(core, Bound, widened, audit):
        assert engine() == "stock"
        assert core.infer(selected_evidence=engine) == "wider"
    assert engine() == "stock" and core.infer is infer
    assert audit == dict(inferences=1, stock_selected_packets=1, counts=dict(calls=1, activated=1), attempts=1, activations=1)


def test_inference_exception_propagates_through_zero_activity_scope():
    def fail(**kwargs):
        raise ArithmeticError("original solver failure")

    class Bound:
        def __call__(self):
            return "stock"

    @contextmanager
    def widened():
        yield {"calls": 0, "activated": 0}

    core, audit = SimpleNamespace(infer=fail), {}
    with pytest.raises(ArithmeticError, match="original solver failure"), inference_scope(core, Bound, widened, audit):
        core.infer()
    assert core.infer is fail
    assert audit["attempts"] == audit["activations"] == audit["stock_selected_packets"] == 0
