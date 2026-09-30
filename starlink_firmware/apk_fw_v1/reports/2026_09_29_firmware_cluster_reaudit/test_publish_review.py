import hashlib

import pytest
from publish_review import checked_entries, render_entry


def test_review_rejects_stale_sources_and_duplicate_ids(tmp_path):
    source = tmp_path / "receipt.json"
    source.write_text("{}")
    row = dict(id="a", scope="DS10", kind="pair", evidence={},
               source=dict(path=str(source), sha256=hashlib.sha256(b"{}").hexdigest()),
               ranked_interpretations=["unresolved"], firmware_constraint="unknown",
               falsifier="held transfer", test_status="negative")
    assert len(checked_entries(dict(associations=[row]))[0]) == 1
    with pytest.raises(ValueError, match="Duplicate"):
        checked_entries(dict(associations=[row, row]))
    source.write_text('{"changed":true}')
    with pytest.raises(ValueError, match="hash mismatch"):
        checked_entries(dict(associations=[row]))


def test_review_preserves_coordinates_and_escapes_evidence():
    row = dict(id="<script>", scope="DS10", kind="pair", evidence={"x": "</pre>"},
               source={}, coordinates=[[3, 515], [3, 520]], parity=1,
               ranked_interpretations=["a", "b"], firmware_constraint="unknown",
               falsifier="transfer", test_status="negative")
    rendered = render_entry(row)
    assert "<script>" not in rendered and "&lt;script&gt;" in rendered
    assert "coordinates" in rendered and "515" in rendered and "parity" in rendered


def test_shared_firmware_receipt_is_checked_without_association_rows(tmp_path):
    source = tmp_path / "firmware-receipt.json"
    source.write_text("{}")
    ledger = dict(associations=[], shared_firmware_constraint=dict(source=dict(
        path=str(source), sha256="sha256:" + hashlib.sha256(b"{}").hexdigest())))
    assert len(checked_entries(ledger)[1]) == 1
    source.write_text("[]")
    with pytest.raises(ValueError, match="hash mismatch"):
        checked_entries(ledger)
