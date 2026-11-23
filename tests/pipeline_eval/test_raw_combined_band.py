"""Protect the combined transfer's predeclared selection and frozen implementation identity."""

from raw_band_pair import selection
from raw_combined_band import BAND, BASE, CFO_FLAG, COMBINED_FLAGS, CURVATURE, EXTRA_SOURCES, PROTOCOL_SHA, receiver_configuration
from same_build_raw_panel import implementation
from short_cfo_raw import EXTENSION_SHA256, LIBRARY_SHA256, POLICY_SHA256


def test_first_combined_band_is_unique_and_candidate_first():
    census = selection(BAND, checkout=BASE, protocol_sha256=PROTOCOL_SHA)
    assert census["cohort_size"] == 455
    assert census["eligible"] == [dict(dataset_label="DS30-0340", issued_visits=555)]
    assert BAND.inputs.workload.order == ("candidate", "stock")
    assert BAND.inputs.workload.compressed_bytes == 686_440_127 < BAND.inputs.workload.raw_limit


def test_combined_implementation_binds_actual_recipe_library_and_policy_sources():
    receiver = receiver_configuration()
    config = receiver["recipe"]["fixed_epoch_cfo_refinement"]
    assert (config["library_sha256"], config["policy_sha256"], config["extension_sha256"]) == (
        LIBRARY_SHA256, POLICY_SHA256, EXTENSION_SHA256,
    )
    assert {CURVATURE, CFO_FLAG} <= set(COMBINED_FLAGS)
    assert {"short_cfo_raw.py", "short_cfo_refine.py", "short_cfo_refine.inc"} <= set(EXTRA_SOURCES)
    pinned = dict(stock={}, route_flags=COMBINED_FLAGS, library_sha256={"cfo_refinement": LIBRARY_SHA256}, sources={}, host={})
    assert implementation(pinned | {"receiver_configuration": receiver}) != implementation(pinned)
