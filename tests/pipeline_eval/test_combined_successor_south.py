import pytest

from reports.ALGO08.v3.combined_successor_south import deny_waveform, figures_and_grid, mirror_requests


def test_mirrored_request_changes_only_the_offer():
    inside = dict(offer_file="inside", offer_sha256="one", native_sha256="native", archive="original")
    outside = inside | dict(offer_file="outside", offer_sha256="two")
    mirror_requests(inside, outside)

    for invalid in (inside, outside | {"archive": "different"}, outside | {"native_sha256": "wrong"}):
        with pytest.raises(ValueError, match="change only the supplied region"):
            mirror_requests(inside, invalid)


def test_saved_guard_blocks_recording_metadata_and_waveforms(tmp_path):
    recording = tmp_path/"original"
    guard = deny_waveform(recording)
    guard("open", (str(tmp_path/"saved.json"),))
    for path in (recording/"manifest.json", tmp_path/"iq-0.ci16.zst"):
        with pytest.raises(ValueError, match="may not open waveform"):
            guard("open", (str(path),))


def test_publication_must_have_null_arms_and_no_products_when_withheld():
    offer = {"width_km": 25}
    term = dict(decision="withheld", region=offer, arms={k: {"latlon": None} for k in ("c0", "fitted_c")})
    run = dict(terminal=term, products={"images": {}}, sample=None, path=None, rows={},
               science={"receipt": {"decision": "withheld"}})
    assert figures_and_grid(run, offer) is None

    with pytest.raises(ValueError, match="zero position products"):
        figures_and_grid(run | {"products": {"images": {"position": "unexpected"}}}, offer)
    with pytest.raises(ValueError, match="original ones"):
        figures_and_grid(run, {"width_km": 20})


def test_complete_legacy_numerical_terminal_keeps_public_contract():
    offer = {"width_km": 25}
    image = {"sha256": "position"}
    binding = {"position_png_sha256": "position"}
    run = {"terminal": {"decision": "ok", "arms": {"c0": {}, "fitted_c": {}}, "region": offer},
           "science": {"receipt": {"decision": "complete"}}, "products": {"images": {"position": image} | {str(i): {} for i in range(7)}},
           "path": {"binding": binding, "stages": [{}]},
           "sample": {"binding": binding, "matched_c_grid": True, "complete": True, "evaluated_points": 1, "points": [{}]}}
    assert figures_and_grid(run, offer) == 1
    with pytest.raises(ValueError, match="public decision disagree"):
        figures_and_grid(run | {"science": {"receipt": {"decision": "withheld"}}}, offer)
