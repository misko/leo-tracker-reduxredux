from importlib import import_module
from io import BytesIO
import json

from PIL import Image
import pytest


comparison = import_module("reports.ALGO08.single-core-2x.compare_publications")


def test_elapsed_stage_clocks_partition_the_raw_to_exit_measurement():
    assert comparison.elapsed_stages(2., 7., 10.) == dict(
        launch_to_detections=5., detections_to_terminal=2., terminal_to_exit=3.)
    for clocks in ((-1., 2., 3.), (3., 2., 3.), (1., 3., 2.), (1., 2., float("inf"))):
        with pytest.raises(ValueError, match="timestamps"):
            comparison.elapsed_stages(*clocks)


def test_factor_comparison_counts_lost_and_replaced_measurements():
    row = dict(visit_index=5, receiver_id=0, channel=3, actual_rf_hz=11, valid_start_counter=17,
               candidates=[dict(cfo=12), dict(cfo=15)])
    before = comparison.selected_factors([row])
    after = comparison.selected_factors([dict(row, candidates=[dict(cfo=15), dict(cfo=23)])])
    assert (before & after).total() == (before - after).total() == (after - before).total() == 1
    assert not before & comparison.selected_factors([dict(row, receiver_id=1)])


def test_png_evidence_allows_recompression_and_reports_changed_pixels():
    def pack(color, level):
        stream = BytesIO()
        Image.new("RGBA", (13, 21), color).save(stream, "PNG", compress_level=level)
        return stream.getvalue()

    first = comparison.image_receipt(pack("blue", 0))
    assert first["size"] == [13, 21]
    assert first == comparison.image_receipt(pack("blue", 9))
    assert first != comparison.image_receipt(pack("green", 9))
    with pytest.raises(ValueError):
        comparison.image_receipt(pack("green", 9)[:-9])


def test_different_offers_cannot_be_compared_as_a_matched_pair(tmp_path):
    left = dict(raw_authority="same", receipt=dict(region="a", session_id="same", window_count=2))
    right = dict(left, receipt=dict(left["receipt"], region="b"))
    path = tmp_path / "pair.json"
    path.write_text(json.dumps(dict(runs=dict(baseline=left, candidate=right))))
    with pytest.raises(ValueError, match="different raw inputs or offers"):
        comparison.compare(path)


def test_public_score_uses_one_reference_per_waveform_and_preserves_withholding(tmp_path, monkeypatch):
    pair, key = tmp_path / "pair.json", tmp_path / "key.json"
    pair.write_text(json.dumps(dict(recording="/data/wave")))
    arms = {"c0": {"latlon": [2., 3.]}, "fitted_c": {"latlon": None}}
    monkeypatch.setattr(comparison, "compare",
                        lambda _, **kw: {k: {"arms": arms} for k in ("baseline", "candidate")})
    selections = import_module("reports.ALGO08.single-core-2x.selected_changes")
    monkeypatch.setattr(selections, "compare", lambda *_args, **_kwargs: {"changed": 0})
    answers = {label: dict(recording="wave", truth=[2., 3.]) for label in ("inside", "outside")}
    key.write_text(json.dumps({"answers": answers}))
    scored = comparison.score_public_waveform(pair, key)
    assert scored["error_km"]["candidate"] == {"c0": 0., "fitted_c": None}
    answers["outside"]["truth"] = [-2., 3.]
    key.write_text(json.dumps({"answers": answers}))
    with pytest.raises(ValueError, match="one public reference"):
        comparison.score_public_waveform(pair, key)
