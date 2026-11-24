import importlib
from pathlib import Path

import pytest


@pytest.fixture
def components(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
    return tuple(importlib.import_module(name) for name in ("continued_cfo_first_0016", "continued_cfo_first_0016_score"))


def test_original_scope_rejects_changed_extent_and_dual_antenna_geometry(components):
    receiver, _ = components
    manifest = dict(chunks=[receiver.DECLARATION], receiver_ids=[0, 1], sample_rate_hz=10_000_000, window_ms=20)
    assert receiver.check_manifest(manifest) == receiver.DECLARATION
    for changed in (dict(manifest, receiver_ids=[0]), dict(manifest, chunks=[dict(receiver.DECLARATION, window_count=63)]),
                    dict(manifest, chunks=[dict(receiver.DECLARATION, chunk_index=1)])):
        with pytest.raises(ValueError, match="original first signed 64 visits"):
            receiver.check_manifest(changed)


def test_prefix_comparison_distinguishes_changed_timing_cfo_and_roundoff(components):
    _, score = components
    original = dict.fromkeys(score.ROUNDOFF, 0.) | dict(integer_epoch_sample=100, candidate_rank=0)
    def row(factor):
        return dict(visit_index=3, receiver_id=1, valid_start_counter=1000, actual_rf_hz=10_000_000, candidates=[factor])

    assert score.audit_rows([row(original)], [row(original | {score.CFO: 1e-9})])["material"] == []
    checked = score.audit_rows([row(original)], [row(original | {score.CFO: 1e-3, "integer_epoch_sample": 101})])
    assert checked["material"] == [dict(lane=(3, 1), fields=[score.CFO, "nonroundoff"])]
    with pytest.raises(ValueError, match="counter"):
        score.audit_rows([row(original)], [dict(row(original), valid_start_counter=1001)])


def test_residency_proof_identifies_the_pair_of_member_files(components):
    _, score = components
    census = dict(unavailable={}, observed_members=2, cached_pages=100, observed_file_pages=100)
    observation = dict(clock=dict(exit_code=0, major_faults=1, input_blocks=8), before=census, after=census)
    score.check_clock(observation)
    with pytest.raises(ValueError, match="fully resident"):
        score.check_clock(dict(observation, after=dict(census, cached_pages=99)))
