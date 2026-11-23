from hashlib import sha256
from types import SimpleNamespace

import pytest

from reports.ALGO08.v3 import receiver_ceiling_0169 as trial


def signed_model(**changes):
    fields = dict(chunk_index=0, first_sequence=0, window_count=trial.WINDOWS, compressed_bytes=trial.COMPRESSED,
                  uncompressed_bytes=trial.DECODED, payload_relative_path="iq-000000.ci16.zst",
                  compressed_sha256=trial.PAYLOAD_PIN, index_relative_path="windows-000000.jsonl")
    fields.update(changes)
    return SimpleNamespace(chunks=(SimpleNamespace(**fields), object()), sample_rate_hz=10_000_000,
                           receiver_ids=(0, 1))


@pytest.mark.parametrize("changes", [dict(chunk_index=1), dict(window_count=63), dict(compressed_bytes=82_000_001),
                                      dict(compressed_sha256="sha256:wrong"), dict(index_relative_path="../index")])
def test_only_original_first_member_can_be_staged(changes):
    model = signed_model()
    assert trial.first_member(model) is model.chunks[0]
    with pytest.raises(ValueError):
        trial.first_member(signed_model(**changes))


def test_copy_binds_exact_bytes_and_refuses_wrong_size_and_symlink(tmp_path):
    contents = b"example original compressed bytes"
    source = tmp_path / "member.zst"
    source.write_bytes(contents)
    pin = sha256(contents).hexdigest()
    output = tmp_path / "accepted.zst"
    assert trial.copy_one(source, output, len(contents), pin) == len(contents)
    assert output.read_bytes() == contents
    with pytest.raises(ValueError, match="frozen bounded file"):
        trial.copy_one(source, tmp_path / "wrong-size.zst", len(contents)-1, pin)
    with pytest.raises(ValueError, match="authenticated source"):
        trial.copy_one(source, tmp_path / "wrong-hash.zst", len(contents), "0" * 64)
    alias = tmp_path / "alias.zst"
    alias.symlink_to(source)
    with pytest.raises(OSError):
        trial.copy_one(alias, tmp_path / "copied-alias.zst", len(contents), pin)


def factor(rank, epoch, hz):
    return rank, epoch, 0.0, hz, 0.15, 0.05


def test_factor_comparison_preserves_signed_cfo_rank_and_order():
    a, b = factor(0, 0, -20_000), factor(1, 10, 50_000)
    assert trial.factor_delta([a, b], [b, a]) == dict(common=[[0, 1], [1, 0]], same_rank=2, exact=2,
                                                     order_changed=True, missing=[], new=[])
    after = [factor(1, 13332, -20_250), factor(0, 10, -50_000)]
    assert trial.factor_delta([a, b], after) == dict(common=[[0, 0]], same_rank=0, exact=0,
                                                    order_changed=False, missing=[1], new=[1])


def test_anchor_native_parity_does_not_hide_selection_change():
    base = factor(0, 1, 30_000)
    fields = ("candidate_rank", "integer_epoch_sample", "fractional_epoch_offset_samples",
              "fractional_tracking_cfo_hz", "fractional_exact_score", "fractional_control_score")

    def arm(native, chosen):
        probe = dict(visit_index=0, receiver_id=0, candidates=[dict(zip(fields, base))] if chosen else [])
        packet = dict(clock_anchor={}, delivery_clocks=[], provenance=dict(excluded_windows=[]),
                      source=dict(raw_recording_authority_digest="same", probes=[probe]))
        return dict(iq=["same"], packet=packet, trace=[dict(visit=0, lane=0, mode="full", factors=[native])])

    left, right = arm(base, False), arm(base, True)
    summary = trial.compare(left, right)["by_mode"]["full"]
    assert summary["native_exact"] == 1 and summary["selected_new"] == 1
    with pytest.raises(ValueError, match="altered full native factor bytes"):
        trial.compare(left, arm(factor(0, 1, 30_001), True))
    right["iq"] = ["changed"]
    with pytest.raises(ValueError, match="signed visit authority"):
        trial.compare(left, right)


def test_final_owner_index_preserves_original_order_and_rejects_duplicate_identity():
    rows = [["b", 1, "predictive"], ["a", 2, "conditional"]]
    assert trial.owner_index(rows)["a"] == {"order": 1, "norad": 2, "role": "conditional"}
    with pytest.raises(ValueError, match="identity is duplicated"):
        trial.owner_index([*rows, ["a", 3, "predictive"]])
