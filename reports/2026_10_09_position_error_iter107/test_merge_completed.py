import runpy
from pathlib import Path

import pytest

MODULE = runpy.run_path(str(Path(__file__).with_name("merge_completed.py")))


def test_exact_membership_and_all_phase_count():
    labels = [f"member{i}" for i in range(193)]
    rows = {label: {"paired_terminal": True} for label in labels}
    hashes = {f"phase{i}": "synthetic" for i in range(386)}
    MODULE["validate_membership"](labels, rows, hashes)
    hashes.pop("phase385")
    with pytest.raises(AssertionError):
        MODULE["validate_membership"](labels, rows, hashes)


def test_same_count_foreign_member_and_unfinished_member_rejected():
    labels = [f"member{i}" for i in range(193)]
    rows = {label: {"paired_terminal": True} for label in labels}
    hashes = {f"phase{i}": "synthetic" for i in range(386)}
    rows["foreign"] = rows.pop("member192")
    with pytest.raises(AssertionError):
        MODULE["validate_membership"](labels, rows, hashes)
    rows["member192"] = rows.pop("foreign")
    rows["member192"]["paired_terminal"] = False
    with pytest.raises(AssertionError):
        MODULE["validate_membership"](labels, rows, hashes)


def test_streaming_hash_known_answer(tmp_path):
    path = tmp_path / "receipt"
    path.write_bytes(b"abc")
    assert MODULE["sha"](path) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("dataset", "DS18"),
        ("session_id", "wrong-session"),
        ("exposure", "unseen"),
        ("loader_kind", "different-loader"),
    ],
)
def test_frozen_identity_mismatch_rejected(field, value):
    member = {
        "kind": "historical",
        "member": {"dataset": "DS16", "session_id": "session", "exposure": "consumed"},
    }
    row = {
        "dataset": "DS16",
        "session_id": "session",
        "exposure": "consumed",
        "loader_kind": "historical",
    }
    MODULE["validate_bindings"]([member], {"label": row}, lambda _: "label")
    row[field] = value
    with pytest.raises(AssertionError):
        MODULE["validate_bindings"]([member], {"label": row}, lambda _: "label")
