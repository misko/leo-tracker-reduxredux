from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame
from tools.pipeline_eval import whole_iq
from tools.pipeline_eval.qualification import differential_runtime as qualification
from tools.pipeline_eval.variants import differential_runtime as runtime


@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_uses_only_the_supplied_standard_qin_pair(edge):
    rate = 10_000_000
    exact = qin_edge_pilot_frame(rate, edge)
    control = qin_edge_pilot_frame(rate, edge, symbol_roll=CONTROL_SYMBOL_ROLL)
    assert runtime.template_edge(exact, control, rate) == edge
    with pytest.raises(ValueError, match="standard exact and control"):
        runtime.template_edge(exact, exact, rate)
    with pytest.raises(ValueError, match="10 MS/s"):
        runtime.template_edge(exact, control, rate // 2)


def test_calls_scout_before_detector_with_independent_rank_one_and_absent_hint(monkeypatch):
    samples = np.zeros((200_000, 2, 2), dtype="<i2")
    proposals = [([54, 79], [2.0, 1.0]), ([], [])]
    seen = []

    def original(_samples, include_timings):
        return {"include_timings": include_timings}

    native = SimpleNamespace(analyze=original)

    def scout(raw, edge):
        assert edge == "upper"
        assert raw is samples
        seen.append("scout")
        return proposals

    def hint_factory(port):
        assert port is native

        def hinted(raw, hints, *, timings):
            assert raw is samples and hints == (54, None)
            seen.append("detector")
            return port.analyze(raw, include_timings=timings), [{}, {}]

        return hinted

    monkeypatch.setattr(runtime.hinted_glrt, "HintedCall", hint_factory)
    call = runtime.DifferentialCall(native, "upper", scout=scout)
    result, ranked, trace, timing = call(samples, decode=original, timings=True)
    assert seen == ["scout", "detector"]
    assert result == {"include_timings": True} and ranked is proposals and trace == [{}, {}]
    assert set(timing) == {"scout_cpu_ns", "scout_wall_ns", "native_cpu_ns", "native_wall_ns"}
    assert native.analyze is original


def test_plans_bind_opt_in_module_and_restore_stock_supervisor(tmp_path, monkeypatch):
    original_module, original_service = whole_iq.MODULE, whole_iq.iq_service.MODULE
    written = []
    monkeypatch.setattr(whole_iq, "save_json", lambda *args: written.append(args))

    def fake_stock(*_):
        assert whole_iq.MODULE == qualification.MODULE
        assert whole_iq.iq_service.MODULE == qualification.MODULE
        whole_iq.save_json(tmp_path / "plan.json", {"case": "sealed"})

    monkeypatch.setattr(qualification, "STOCK_EVALUATE", fake_stock)
    qualification.evaluate("sealed", None, qualification.HINTED_SHA256, None, tmp_path, (0, 1), 5)
    assert written[0] == (
        tmp_path / "plan.json",
        {"case": "sealed", "differential_sources": qualification.source_identity()},
    )
    assert original_module == whole_iq.MODULE and original_service == whole_iq.iq_service.MODULE


def test_rejects_other_native_library_before_launch(tmp_path):
    with pytest.raises(ValueError, match="qualified hinted wide library"):
        qualification.evaluate("sealed", None, "unexpected", None, tmp_path, (0, 1), 5)
