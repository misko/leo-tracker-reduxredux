import sys
from types import SimpleNamespace

import pytest

from tools.pipeline_eval.variants import v5_signed_context_memory as signed


def previous_bank(scan, labels):
    return "dense", scan, labels


def phase_widths(scan, labels):
    return previous_bank(scan, labels)


def test_switch_only_signed_consumer_to_the_sampled_inventory(monkeypatch):
    consumer = SimpleNamespace(phase_widths=phase_widths)
    other = SimpleNamespace(phase_widths=phase_widths)
    module = SimpleNamespace(signed_context=consumer, other=other)
    monkeypatch.setitem(sys.modules, "leo.analysis.localization_v3", module)
    monkeypatch.setattr(
        signed.v5_family_memory, "alignment_only", lambda scan, labels: ("sampled", scan, labels)
    )

    with pytest.raises(ValueError, match="stop"), signed.signed_widths():
        assert consumer.phase_widths("scan", [1]) == ("sampled", "scan", [1])
        assert other.phase_widths("scan", [1]) == ("dense", "scan", [1])
        raise ValueError("stop")
    assert consumer.phase_widths is phase_widths
