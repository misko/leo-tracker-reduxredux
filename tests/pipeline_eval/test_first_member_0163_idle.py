import json
from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
import first_member_0163_idle as staged


def test_window_admits_only_the_enrolled_first_member(tmp_path, monkeypatch):
    recording = tmp_path / "recording"
    segment = recording / "first"
    segment.mkdir(parents=True)
    payload = segment / "first.iq"
    payload.touch()
    first = dict(path=str(segment), scope="segment-00000000", manifest_digest="sha256:manifest")
    request = dict(case=staged.CASE, inventory="sha256:" + staged.INVENTORY_PIN, issued=64,
                   recording=str(recording), manifests=[[str(segment / "manifest.json"), first["manifest_digest"]]])
    member = dict(compressed_bytes=staged.SIZE, window_count=64, first_sequence=0,
                  payload_relative_path=payload.name)
    ledger = dict(cases=[dict(case="DS30-0173"), dict(
        case=staged.CASE, first_member=member, signed_first_segment=first,
        cache=dict(device=staged.DEVICE, inode=5))])
    documents = {staged.PREVIOUS: ledger, staged.READY / "request.json": request,
                 staged.READY / "inventory.json": dict(window_count=64, segments=[first])}
    monkeypatch.setattr(staged, "metadata", lambda path, _pin, _limit: json.dumps(documents.get(path)).encode())

    assert staged.bindings() == (request, first, member, payload, 5)
    assert staged.SECONDS == 300
    member["compressed_bytes"] += 1
    with pytest.raises(ValueError, match="enrollment changed"):
        staged.bindings()
