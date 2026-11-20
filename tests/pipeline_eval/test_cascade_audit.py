from math import isclose

from tools.pipeline_eval.qualification import cascade_audit_results as results
from tools.pipeline_eval.qualification import cascade_audit_trial as trial
from tools.pipeline_eval.qualification.factor_cross import CFO, GATE, MARGIN, RANK
from tools.pipeline_eval.scoring import ARMS


def test_audit_one_physical_visit_per_complete_block():
    visits = [i for i in range(91) if i not in (1, 2, 34, 38, 65)]
    probes = [dict(visit_index=i, receiver_id=rx) for i in visits for rx in (0, 1)]
    chosen, n = trial.audit_schedule(probes, "sha256:fixed")
    assert n == len(visits)
    assert len(chosen) == n // 32 == 2
    for block, (visit, pair) in enumerate(chosen):
        offset = int(trial.digest("sha256:fixed", block), 16) % 32
        assert visit == visits[32 * block + offset]
        assert [p["receiver_id"] for p in pair] == [0, 1]


def test_audit_distinguishes_physical_and_alias_agreement():
    def probe(epoch, cfo, margin=0.12):
        return {
            "candidates": [
                {
                    GATE: margin >= 0.025,
                    RANK: 0,
                    MARGIN: margin,
                    CFO: cfo,
                    "integer_epoch_sample": epoch,
                    "fractional_epoch_offset_samples": 0.0,
                }
            ]
        }

    original = probe(0, 6000)
    wrapped_epoch = round(10_000_000 / trial.FRAME_HZ) - 1
    observed = trial.signal(original, probe(wrapped_epoch, 6000), 10_000_000)
    assert observed["outcome"] == "literal"
    assert isclose(observed["epoch_samples"], 1.0)
    aliased = trial.signal(original, probe(wrapped_epoch, 6000 + trial.ALIAS_HZ), 10_000_000)
    assert aliased["outcome"] == "aliased" and aliased["alias_steps"] == -1
    assert trial.signal(original, probe(0, 6000, 0.01), 10_000_000)["outcome"] == "original_only"


def test_development_target_uses_cross_branch_disagreement_and_both_arms():
    def branches(a, b):
        return dict(
            status="ok",
            arms={arm: {"latlon": point} for arm, point in zip(ARMS, (a, b), strict=True)},
        )

    fixed = branches([0, 0], [0, 0])
    assert not trial.requires_original(fixed, branches([0, 0], [0.004, 0]))
    assert trial.requires_original(fixed, branches([0, 0], [0.006, 0]))
    assert trial.requires_original(fixed, branches([0, 0], None))
    assert trial.requires_original(fixed, {"status": "timed_out"})
    assert trial.threshold([(0.1, False), (0.22, True), (0.4, True)]) == 0.22
    assert trial.threshold([(0.5, False)]) > 1


def test_oracle_prioritizes_joint_allowance_coverage_and_can_avoid_bad_switches():
    def mark(hit, error):
        return dict(within_10pct=hit, error_km=error)

    scores = {
        ("a", "fast"): [mark(False, 0.3), mark(False, 0.3)],
        ("a", "original"): [mark(True, 0.1), mark(False, 1.5)],
        ("b", "fast"): [mark(True, 0.1), mark(False, 0.1)],
        ("b", "original"): [mark(False, None), mark(False, 0.4)],
    }
    chosen, order = results.rank_benefit(scores, ["a", "b"])
    assert chosen == ["a"]
    assert order == ["a", "b"]
