from leo.presentation.adaptive_dual_rx_phase_v2 import render_adaptive_dual_rx_phase_v2
from tests.storage.test_adaptive_dual_rx_phase_v2_store import visit


def test_renderer_labels_unresolved_double_difference_hypotheses() -> None:
    payload = render_adaptive_dual_rx_phase_v2((visit(0), visit(1)))
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    assert payload.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82")
    assert len(payload) > 1_000
