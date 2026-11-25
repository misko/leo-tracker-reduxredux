import pytest

from reports.ALGO08.v3 import grid_export_publication_audit as audit


def test_archives_separate_the_component_receipt_from_actual_publications():
    result = audit.report()
    valid, near = (result["charted_south"][key] for key in ("containing", "near-omitted"))
    assert valid["input_sha256"] == near["input_sha256"]
    assert valid["terminal_sha256"] != near["terminal_sha256"]
    assert valid["clearance_km"] > 0 > near["clearance_km"]
    for positive in (valid, near):
        assert positive["owners"] == {arm: 304 for arm in audit.ARMS}
        assert positive["points"] == 137 and positive["images"] == 8
        assert positive["stock_factors"] == 272 and positive["route"] == "lean"
        assert not positive["guard"]["evaluated"]
    assert result["installed_south_far"]["science"] == {}
    far = result["earlier_north_far"]
    assert far["artifacts"] == [] and far["grid"] is None and not far["posterior_grid_calls"]


@pytest.mark.parametrize(("field", "pattern"), [
    ("position_hash", "must bind"),
    ("image_absent", "all eight products"),
    ("owner_changed", "must bind"),
])
def test_integrated_receipt_rejects_unbound_products(field, pattern):
    offer = audit.checked("v3/measurements/integrated-south.json.gz")["offers"]["containing"]
    if field == "position_hash":
        offer["sidecars"]["binding"]["position_png_sha256"] = "wrong"
    if field == "image_absent":
        offer["images"].pop("track-rms")
    if field == "owner_changed":
        offer["witness"]["evidence"]["owner_rows"]["c0"][0][1] = 0
    with pytest.raises(ValueError, match=pattern):
        audit.integrated(offer)
