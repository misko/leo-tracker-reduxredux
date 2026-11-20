from threading import Lock

import pytest

from tools.pipeline_eval.qualification import staggered_native_build as build
from tools.pipeline_eval.qualification import staggered_native_eval as witness
from tools.pipeline_eval.variants.staggered_native import RfStagger, StaggeredLane


def test_rf_stagger_counts_valid_arrivals_independently():
    select = RfStagger()
    a, b = 10_709_687_500, 11_395_312_500
    assert select.reserve(None, valid=False) is None
    assert select.reserve(a) == 0
    assert select.reserve(b) == 0
    assert select.reserve(b, valid=False) is None
    assert select.reserve(a) == 1
    assert select.reserve(b) == 1
    assert select.reserve(a) == 0
    assert RfStagger().reserve(a) == 0
    with pytest.raises(ValueError, match="integer hertz"):
        select.reserve(float(b))
    assert select.reserve(b) == 0


def test_staggered_port_preserves_scope_after_a_failed_native_call():
    port = object.__new__(StaggeredLane)
    port.lock = Lock()
    port._selected = None

    def analyze(samples, mode, trace):
        assert mode == "stock"
        assert port._selected == 1
        if samples is None:
            raise RuntimeError("observed native failure")
        return {"rows": []}, {"lanes": []}

    port._analyze = analyze
    assert port.mixed(0, 1, trace=True)[1]["fifth_lane"] == 1
    assert port._selected is None
    with pytest.raises(RuntimeError, match="observed native failure"):
        port.mixed(None, 1)
    assert port._selected is None
    for invalid in (-1, 2, True, 1.0):
        with pytest.raises(ValueError, match="physical receiver"):
            port.mixed(0, invalid)


def test_compiled_overlay_preserves_symmetric_branches_and_limits_the_new_selector():
    original = build.lane.LANE_C.read_text()
    changed = build.graft(original)
    assert changed.count(f"int {build.ORIGINAL}(") == 1
    assert changed.count(f"int {build.SYMBOL}(") == 1
    assert "analyze_pair(ctx, mode, mode, iq, count, out, trace)" in changed
    assert "if (fifth_lane != 0 && fifth_lane != 1)" in changed
    assert "ctx->mode = second;" in changed
    assert (
        changed.split("static void *second_lane", 1)[0]
        == original.split("static void *second_lane", 1)[0]
    )


def test_pair_validation_compares_each_physical_lane_models_and_traces():
    lane0 = {"row": "four0", "hint": -1, "support": []}
    lane1 = {"row": "five1", "hint": 735, "support": [734, 735, 736]}
    roles = {"four": [lane0, {}], "five": [{}, lane1], "mixed": [lane0, lane1]}
    assert witness.check_mixed(roles, 1)
    assert not witness.check_mixed(roles, 0)
    assert not witness.check_mixed(roles | {"mixed": [lane0, lane1 | {"support": []}]}, 1)
