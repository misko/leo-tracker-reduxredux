from hashlib import sha256
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
sys.path.insert(0, str(HERE))

from stereo_lane_schedule import StereoSchedule, recipe


@pytest.mark.parametrize("mode, omitted", [
    ("quarter", [(2, 1), (4, 1), (6, 0), (9, 0)]),
    ("target", [(2, 1), (3, 0), (4, 1), (6, 0), (7, 1), (9, 0)]),
])
def test_mask_preserves_stereo_anchors_balances_lanes_and_keeps_an_independent_stream(mode, omitted):
    schedule = StereoSchedule(mode)
    left, right = ("lower", 2, 11_000_000_000), ("upper", 2, 11_000_000_000)
    rows = [schedule.next(left) for _ in range(10)]
    assert [i for i, (aperture, _) in enumerate(rows) if aperture == "full"] == [0, 8]
    assert [(i, radio) for i, (_, radio) in enumerate(rows) if radio is not None] == omitted
    assert schedule.next(right) == ("full", None)
    assert schedule.next(right) == ("short_primary", None)
    assert schedule.next(right) == ("short_primary", 1)
    assert schedule.next(left) == ("short_primary", None)
    assert schedule.next(left) == ("short_primary", 1)


def test_recipe_binds_schedule_bytes_and_parent():
    parent = "sha256:" + "e"*64
    assert recipe("target", parent)["source_sha256"] == sha256((HERE / "stereo_lane_schedule.py").read_bytes()).hexdigest()
    assert recipe("target", parent)["parent_receiver"] == parent
    assert recipe("target", parent) != recipe("quarter", parent)
    with pytest.raises(ValueError, match="original canonical"):
        recipe("target", "e"*64)


def test_saved_projection_never_infers_missing_data_or_changes_a_paid_lane():
    from leo.contracts.digests import canonical_digest
    from stereo_mask_trial import RECIPE_SHA, native_signature, project

    probes = [dict(visit_index=n, receiver_id=r, edge="upper", channel=1, actual_rf_hz=11_000_000_000,
                   valid_start_counter=n*10_000_000, payload_start_sample=0,
                   candidates=[dict(fractional_tracking_cfo_hz=4000 + 20*n + r)])
              for n in range(10) for r in (0, 1)]
    source = dict(probes=probes, sample_rate_hz=10_000_000, qualified=True, session_id="fixture",
                  raw_recording_authority_digest="sha256:"+"e"*64)
    original = "sha256:" + RECIPE_SHA
    source["analysis_manifest_sha256"] = native_signature(source, original, probes)
    provenance = dict(detector_sha256=original, scope="cancellation", window_count=10,
                      processed_windows=10, excluded_windows=[])
    native = dict(source=source, provenance=provenance, delivery_clocks=[{} for _ in range(10)])

    masked, audit = project(native, "target")
    assert audit["skipped_native_lanes"] == {"short_primary": 6}
    assert audit["kept_native_lanes"] == {"full": 4, "short_primary": 10}
    assert audit["lost_factors_by_radio"] == {0: 3, 1: 3}
    assert audit["mask_sha256"] == canonical_digest(audit["skipped_slots"])
    assert masked["provenance"]["detector_sha256"] == canonical_digest(recipe("target", original))
    skipped = set(audit["skipped_slots"])
    for old, current in zip(probes, masked["source"]["probes"], strict=True):
        if (old["visit_index"], old["receiver_id"]) in skipped:
            assert current == dict(old, candidates=[])
            assert old["candidates"]
        else:
            assert current == old


def test_member_revisit_uses_exclusive_boundaries_and_counts_each_member_once():
    from stereo_mask_score import member_revisit

    members = [dict(stop=n, compressed=10, decoded=20, index=2) for n in (64, 128, 192)]
    result = member_revisit(members, ((63, 0), (64, 1), (64, 0)))
    assert result == dict(revisit_members=2, total_members=3, member_ids=[0, 1], compressed_bytes=20,
                          decoded_bytes=40, index_bytes=4)
    with pytest.raises(ValueError, match="outside the signed capture"):
        member_revisit(members, ((192, 0),))
