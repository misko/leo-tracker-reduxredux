import pytest

import leo.scanner.adaptive_hop_analysis as detector
from leo.application.adaptive_hop_analysis import AdaptiveHopAnalysisService
from leo.application.adaptive_hop_overview import AdaptiveHopOverviewService
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from tests.application.test_adaptive_hop_analysis import Inputs
from tests.presentation.adaptive_overview_fixtures import rendered_fixture
from tests.scanner.test_persistent_hop_standard_analysis import _fake_fractional_dwell


def test_overview_retries_without_iq_reads_or_repeated_analysis(monkeypatch, tmp_path):
    inputs, products = Inputs(), AdaptiveHopAnalysisStore(tmp_path)
    session = inputs.reader.session_id
    monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
    AdaptiveHopAnalysisService(inputs=inputs, products=products).analyze_session(session)
    inputs.reader.calls.clear()
    seen = []

    def renderer(binding, manifest, visits):
        seen.append(tuple(visits))
        if len(seen) == 1:
            raise RuntimeError("injected render failure")
        return rendered_fixture()

    service = AdaptiveHopOverviewService(inputs=inputs, products=products, renderer=renderer)
    with pytest.raises(RuntimeError, match="injected"):
        service.render_session(session)
    result = service.render_session(session)
    assert result == service.render_session(session)
    assert inputs.reader.calls == [] and len(seen) == 2 and len(seen[0]) == 3
    assert inputs.opened == inputs.closed == 4
    products.close()


def test_incomplete_metrics_cannot_render(monkeypatch, tmp_path):
    inputs, products = Inputs(), AdaptiveHopAnalysisStore(tmp_path)
    monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
    AdaptiveHopAnalysisService(inputs=inputs, products=products).analyze_session(
        inputs.reader.session_id, maximum_visits=1
    )
    service = AdaptiveHopOverviewService(
        inputs=inputs,
        products=products,
        renderer=lambda *args: pytest.fail("unsealed metrics cannot render"),
    )
    with pytest.raises(ValueError, match="finalized metrics"):
        service.render_session(inputs.reader.session_id)
    products.close()
