from types import SimpleNamespace

import pytest

from tools.pipeline_eval import original_receiver
from tools.pipeline_eval.qualification.first_gate_trial import cutoff_projections
from tools.pipeline_eval.variants.first_gate import GATE, GateStop


@pytest.mark.parametrize("limit,expected", [(1, [0, 1]), (2, [0, 1, 2, 3])])
def test_fractional_cutoff_executes_only_required_ranked_scores(limit, expected):
    margins = (None, GATE, 0.003, 0.03, 0.04)
    ranked = tuple(
        SimpleNamespace(rank=r, refined_epoch_sample=r, absolute_cfo_hz=15.0 * r)
        for r in range(len(margins))
    )
    calls = []
    score = SimpleNamespace(
        residual_cfo_hz=10.0,
        tracking_cfo_hz=12.0,
        exact_score=0.05,
        control_score=0.01,
        margin=0.04,
    )

    def integer(_probe, _rate, *, epoch_samples, acquired_cfo_hz, edge):
        calls.append(("integer", epoch_samples))
        return (score,) * len(epoch_samples)

    def fractional(_probe, _rate, *, integer_epoch_samples, expected_integer_scores, **_):
        (rank,) = integer_epoch_samples
        assert expected_integer_scores == (score,)
        calls.append(("fractional", rank))
        return (
            SimpleNamespace(
                status=SimpleNamespace(
                    value="complete" if margins[rank] is not None else "partial"
                ),
                fractional_epoch_offset_samples=0.1,
                fractional_frame_phase_sample=rank + 0.1,
                fractional_exact_score=0.06,
                fractional_control_score=0.01,
                fractional_residual_cfo_hz=2.0,
                fractional_tracking_cfo_hz=3.0,
                fractional_margin=margins[rank],
            ),
        )

    detector = SimpleNamespace(
        _evaluate_probe=None,
        acquire_symbolwise=lambda *_args, **_kwargs: SimpleNamespace(candidates=ranked),
        conditioned_glrt64_scores=integer,
        refine_glrt64_epochs=fractional,
        Glrt64CandidateResponse=SimpleNamespace,
        _ProbeEvaluation=lambda responses, hits: SimpleNamespace(candidates=responses, hits=hits),
    )
    config = SimpleNamespace(
        scheduled_probe_count=1,
        glrt64_margin_gate=GATE,
        sample_rate_hz=10_000_000,
        maximum_acquisition_candidates=len(ranked),
    )
    gate = GateStop(detector, limit)
    with gate.route():
        result = detector._evaluate_probe(
            None, config, None, edge="upper", acquisition_config=None, receiver_id=1, probe_index=0
        )
        assert [r.candidate_rank for r in result.candidates] == expected
        assert [r.fractional_margin for r in result.candidates] == [margins[i] for i in expected]
        assert all(r.passed_margin_gate for r in result.candidates)
    assert detector._evaluate_probe is None
    assert calls == [("integer", tuple(range(len(ranked))))] + [("fractional", i) for i in expected]


def test_numerical_projection_keeps_rank_holes_and_complete_misses():
    public = dict(
        receivers=[
            dict(
                candidates=[
                    dict(rank=0, fractional_margin=None),
                    dict(rank=1, fractional_margin=0.02),
                    dict(rank=2, fractional_margin=GATE),
                    dict(rank=3, fractional_margin=0.03),
                ]
            )
        ]
    )
    probes = [
        dict(
            candidates=[
                dict(candidate_rank=1, passed_fractional_margin_gate=False),
                dict(candidate_rank=2, passed_fractional_margin_gate=True),
                dict(candidate_rank=3, passed_fractional_margin_gate=True),
            ]
        ),
        dict(candidates=[dict(candidate_rank=7, passed_fractional_margin_gate=False)]),
    ]
    shortened, projected = cutoff_projections((public, probes), 1)
    assert [r["rank"] for r in shortened["receivers"][0]["candidates"]] == [0, 1, 2]
    assert [r["candidate_rank"] for r in projected[0]["candidates"]] == [1, 2]
    assert projected[1] == probes[1]
    assert cutoff_projections((public, probes), 2) == (public, probes)


def test_stop_rejects_unsupported_probe_schedule_before_acquisition():
    detector = SimpleNamespace(_evaluate_probe=None)
    gate = GateStop(detector, 1)
    with pytest.raises(ValueError, match="single-probe"):
        gate.evaluate(
            None,
            SimpleNamespace(scheduled_probe_count=2),
            None,
            edge="lower",
            acquisition_config=None,
            receiver_id=0,
            probe_index=0,
        )
    with pytest.raises(ValueError, match="first or second"):
        GateStop(detector, True)


@pytest.mark.parametrize("option", [None, "full", "first", "second"])
def test_saved_receiver_enables_only_an_explicit_rank_stop(tmp_path, monkeypatch, option):
    out = tmp_path / "receipt"
    monkeypatch.setattr(original_receiver, "input_case", lambda *_: {"id": "fixture"})

    def prepare(*args, **options):
        assert options.pop("fractional_stop", "full") == (option or "full")
        assert options["fine_backend"] == "pruned" and options["peak_selector"] == "row-wise"
        assert options["interior_guard"] is True
        out.mkdir()
        return dict()

    monkeypatch.setattr(original_receiver, "prepare", prepare)
    monkeypatch.setattr(
        original_receiver, "run", lambda *_: dict(id="fixture", status="stage_only", stage="raw")
    )
    args = [
        "--case",
        "fixture",
        "--out",
        str(out),
        "--cpus",
        "6",
        "--smoke",
        "--peak-selector",
        "row-wise",
        "--fine-search",
        "pruned",
        "--interior-guard",
    ]
    if option is not None:
        args += ["--fractional-stop", option]
    assert original_receiver.main(args) == 0


def test_stop_source_gate_and_bounded_work_tally(tmp_path):
    assert original_receiver.fractional_stop_for({}) is None
    with pytest.raises(ValueError, match="unqualified for producer"):
        original_receiver.fractional_stop_evidence("second", tmp_path)
    tally = original_receiver.GateAttemptTally()
    tally.append((0, 0, 8, tuple(range(8))))
    tally.append((1, 0, 8, (0,)))
    assert tally.counts == dict(attempts=2, available=16, evaluated=9, shortened_attempts=1)
