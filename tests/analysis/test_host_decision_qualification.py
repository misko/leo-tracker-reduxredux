"""Qualification verdict support and evidence preservation, without corpus I/O."""

from types import SimpleNamespace

import pytest

from tools.qualify_host_adaptive_decisions import verdict, write_new


@pytest.mark.parametrize(
    "window,epoch,complete,score,expected",
    [
        (0, 41, True, 0.9, "unknown"),
        (0, 42, True, 0.9, "detected"),
        (1, 0, True, 0.9, "detected"),
        (5, 50, False, 0.9, "unknown"),
        (5, 50, True, 0.1, "not_detected"),
    ],
)
def test_reference_verdict_requires_supported_fractional_confirmation(
    window,
    epoch,
    complete,
    score,
    expected,
):
    c = SimpleNamespace(epoch=epoch, fractional_complete=complete, exact_score=score, margin=0.1)
    result = SimpleNamespace(
        rank=SimpleNamespace(order=[window]),
        confirmations=[SimpleNamespace(candidates=[c], candidate_count=1)],
    )
    assert verdict(result, 40) == expected


def test_evidence_cannot_be_overwritten(tmp_path):
    path = tmp_path / "sealed.json"
    write_new(path, {"value": 1})
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        write_new(path, {"value": 2})
    assert path.read_bytes() == original
