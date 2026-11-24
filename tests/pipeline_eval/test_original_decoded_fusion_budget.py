import hashlib
import json

import pytest

from reports.ALGO08.v3 import original_decoded_fusion_budget as budget


def test_sealed_current_receipts_have_disjoint_decoder_and_short_bounds():
    result = budget.reduce()
    assert json.loads((budget.MEASURES / "original-decoded-fusion-budget.json").read_bytes()) == json.loads(json.dumps(result))
    assert result["original_first_member"]["demanded_aperture_bytes"] == 44_800_000
    assert result["original_first_member"]["timing"]["cpu_s"]["decoded_sha"] == pytest.approx(.024230167)
    assert len(result["scenarios"]) == 2
    for order in result["scenarios"].values():
        assert order["first_window_sha_payload_block_reuse_ceiling"] < .0084
        optimistic = order["optimistic"]
        assert optimistic["all_outside_native"]["remaining_to_half_s"] > 0
        assert optimistic["all_short_native"]["remaining_to_half_s"] > .4
        assert optimistic["decoder_and_decoded_sha"]["remaining_to_half_s"] > .4
        for source in order["recordings"].values():
            for row in source["timing"].values():
                assert row["acquisition"] == pytest.approx(row["outside_native"] + sum(row["native"].values()))
                assert row["outside_native"] == pytest.approx(sum(row[key] for key in (
                    "decoder_including_checksum", "decoded_sha", "encoded_main", "other_outside_native")))


def test_first_window_state_can_fork_across_unaligned_and_empty_extents():
    for first in (b"", bytes(range(111)), bytes(range(128))):
        following = bytes(range(93))
        whole = hashlib.sha256(first)
        check = whole.copy().digest()
        whole.update(following)
        assert check == hashlib.sha256(first).digest()
        assert whole.digest() == hashlib.sha256(first + following).digest()


def test_reducer_rejects_an_unpinned_archive(monkeypatch, tmp_path):
    monkeypatch.setattr(budget, "MEASURES", tmp_path)
    (tmp_path / "integrated-original.json.gz").write_bytes(b"different archive")
    with pytest.raises(ValueError, match="Clock receipt pin"):
        budget.recorded("integrated-original")
