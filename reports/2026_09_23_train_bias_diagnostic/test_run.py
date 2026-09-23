import importlib.util
from pathlib import Path

import numpy as np
import pytest

PATH = Path(__file__).with_name("run.py")
SPEC = importlib.util.spec_from_file_location("train_bias_run", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_inverse_offset_round_trip():
    centre = (38.5, -121.3)
    for expected in ((0.0, 0.0), (12.3, -7.4), (-280.0, 190.0)):
        point = MODULE.load(MODULE.SINGLE, "bias_test_single").offset_coordinate(centre, *expected)
        np.testing.assert_allclose(MODULE.inverse_offset(centre, point), expected, atol=1e-9)


def test_alignment_extremes():
    assert np.isclose(MODULE.alignment([[1, 0], [2, 0]]), 1.0)
    assert np.isclose(MODULE.alignment([[1, 0], [-1, 0]]), 0.0)


def test_block_partition_is_exact_and_disjoint():
    groups = [[f"a{i}" for i in range(7)], [f"b{i}" for i in range(9)]]
    blocks = MODULE.block_partition(groups)
    assert len(blocks) == 8
    assert [sid for row in blocks for sid in row["session_ids"]] == groups[0] + groups[1]


def test_cache_binding_tamper_is_rejected(tmp_path):
    session = tmp_path / "scan"
    session.mkdir()
    receipt = session / "cache_receipt.json"
    cache = session / "state_cache.npz"
    receipt.write_text("receipt")
    cache.write_text("cache")
    bindings = [
        {
            "session_id": "scan",
            "receipt": MODULE.digest(receipt),
            "cache": MODULE.digest(cache),
        }
    ]
    MODULE.verify_cache_bindings(tmp_path, bindings)
    cache.write_text("tampered")
    with pytest.raises(ValueError, match="cache binding mismatch"):
        MODULE.verify_cache_bindings(tmp_path, bindings)
