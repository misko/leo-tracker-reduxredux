from importlib import import_module
from hashlib import sha256
import json
from pathlib import Path

import pytest


def test_only_requested_stereo_buffers_but_entire_compressed_member(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    footprint = import_module("rf_block_storage").footprint
    members = [(12, {0: 8, 1: 9}), (10, {2: 12, 3: 6})]
    assert footprint(members, {2}) == dict(stereo_visits=1, held_iq_bytes=12, touched_members=1,
                                            member_compressed_bytes=10, member_decoded_bytes=18)
    assert footprint(members, {0, 2})["member_compressed_bytes"] == 22
    with pytest.raises(ValueError, match="absent"):
        footprint(members, {4})
    with pytest.raises(ValueError, match="Repeated"):
        footprint([*members, members[1]], {2})


def test_second_pass_is_bound_to_the_saved_frequency_proposals():
    root = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3/measurements"
    pin = sha256((root / "sparse-rf-visits.json.gz").read_bytes()).hexdigest()
    rows = json.loads((root / "rf-block-storage.json").read_bytes())
    for case in rows.values():
        assert case["forecast_archive_sha256"] == pin
        for by_rule in case["forecast"].values():
            for evidence in by_rule.values():
                assert evidence["held_iq_bytes"] <= case["unpaid"]["held_iq_bytes"]
                assert evidence["member_compressed_bytes"] <= case["all_members"]["member_compressed_bytes"]
    assert rows["DS30-0008"]["forecast"]["fitted_c"]["receiver_transfer"]["touched_members"] == 77
