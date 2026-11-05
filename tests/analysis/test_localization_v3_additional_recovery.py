from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import additional_recovery as recovery
from leo.analysis.localization_v3 import residual_position as position

ARMS = ("c0", "fitted_c")


def target(identity="a", norad=2, points=30, margin=20):
    return dict(
        source=dict(fragment_id=identity, points=points),
        summaries=[
            dict(
                policy="72h_30s",
                screen_pass=True,
                arms={
                    arm: dict(
                        folds={
                            name: dict(margin=margin, winner=dict(norad=norad, alias=0))
                            for name in ("full", "held")
                        }
                    )
                    for arm in ARMS
                },
            )
        ],
    )


def test_selection_uses_worst_fold_then_points_then_identity_and_both_owner_arms():
    rows = [
        target("c"),
        target("b"),
        target("a", points=29),
        target("d", margin=21),
        target("existing", norad=3, margin=100),
    ]
    owners = dict(c0={"p": 1}, fitted_c={"q": 3})
    rows[3]["summaries"][0]["arms"]["fitted_c"]["folds"]["held"]["margin"] = 9
    option, decision = recovery.choose_target(dict(targets=rows), owners, 1)
    assert option[2] == "b"
    assert decision["eligible_proposals"] == 3
    assert decision["excluded"][0]["norad"] == 3
    option, decision = recovery.choose_target(dict(targets=rows), owners, 2)
    assert option is None and decision["eligible_proposals"] == 0


@pytest.mark.parametrize(
    "control_pass,candidate_pass,expected",
    [
        (True, True, "qualified"),
        (False, True, "rejected"),
        (True, False, "rejected"),
    ],
)
def test_addition_requires_both_arms_of_fresh_control_and_candidate(
    monkeypatch, control_pass, candidate_pass, expected
):
    contexts, calls, delivered = [], [], []

    def fresh():
        context = dict(families=[], scan=object(), model=object())
        contexts.append(context)
        return context

    def fit(owners, context, extra, *, deadline, clock, on_arm):
        calls.append((context, extra, deadline))
        rows = {arm: dict(all_checked_gates_pass=True) for arm in ARMS}
        rows["fitted_c"]["all_checked_gates_pass"] = candidate_pass if extra else control_pass
        for arm, row in rows.items():
            on_arm(arm, row)
        return rows

    monkeypatch.setattr(recovery, "fit_pair", fit)
    monkeypatch.setattr(recovery, "add_target", lambda *a: dict(points=30))
    monkeypatch.setattr(recovery, "prediction_scan", lambda scan, bound: scan)
    monkeypatch.setattr(recovery, "NewFamily", lambda *a, **kw: SimpleNamespace(receipt=kw))
    result = recovery.recover_additional(
        fresh,
        {arm: {} for arm in ARMS},
        dict(case="SCAN", targets=[target()]),
        {},
        [],
        family_count=0,
        clock=lambda: 100,
        on_arm=lambda *args: delivered.append(args),
    )
    assert result["decisions"]["72h_30s"]["status"] == expected
    assert len(contexts) == 2 and contexts[0] is not contexts[1]
    assert calls[0][0] is contexts[0] and calls[1][0] is contexts[1]
    assert [c[2] for c in calls] == [700, 700]
    assert len(delivered) == 4


def test_empty_screen_does_not_reconstruct_or_fit():
    result = recovery.recover_additional(
        lambda: pytest.fail("Unnecessary reconstruction"),
        {a: {} for a in ARMS},
        dict(case="SCAN", targets=[]),
        {},
        [],
        family_count=0,
        clock=lambda: 0,
    )
    assert result["control"] is None and result["trials"] == {}


def test_failed_candidate_does_not_become_accepted(monkeypatch):
    monkeypatch.setattr(
        recovery,
        "fit_pair",
        lambda *a, **kw: {arm: dict(all_checked_gates_pass=True) for arm in ARMS},
    )
    monkeypatch.setattr(recovery, "add_target", lambda *a: dict(points=30))

    def fail(*a):
        raise ValueError("orbit propagation failed")

    monkeypatch.setattr(recovery, "prediction_scan", fail)
    result = recovery.recover_additional(
        lambda: dict(families=[], scan=object()),
        {a: {} for a in ARMS},
        dict(case="SCAN", targets=[target()]),
        {},
        [],
        family_count=0,
        clock=lambda: 0,
    )
    assert result["decisions"]["72h_30s"]["status"] == "failed_closed"


def test_control_timeout_propagates_before_candidate_construction(monkeypatch):
    def timeout(*a, **kw):
        raise TimeoutError("control exhausted")

    monkeypatch.setattr(recovery, "fit_pair", timeout)
    monkeypatch.setattr(recovery, "add_target", lambda *a: pytest.fail("Candidate after timeout"))
    with pytest.raises(TimeoutError, match="control exhausted"):
        recovery.recover_additional(
            lambda: dict(families=[]),
            {a: {} for a in ARMS},
            dict(case="SCAN", targets=[target()]),
            {},
            [],
            family_count=0,
            clock=lambda: 0,
        )


def test_whole_track_candidate_preserves_selected_scan_and_mutable_caches():
    track = dict(observation_ids=["a", "b"], key="RX1_CH1_T001")
    scan = SimpleNamespace(
        norads=np.array([2]),
        tracks=[track],
        reference={"old": 1},
        causal_uncertainty_modes={"cached": object()},
    )
    context = dict(scan=scan)
    entry = position.add_target(
        context,
        dict(track_index=0, source_local_indices=[0, 1], observation_ids=["a", "b"]),
        dict(norad=2, alias=0),
        dict(elements={"2": {}}),
        [],
        {a: {} for a in ARMS},
    )
    assert entry["points"] == 2 and entry["candidate_index"] == 0
    assert context["scan"] is not scan
    context["scan"].reference["new"] = 2
    context["scan"].causal_uncertainty_modes.clear()
    assert scan.reference == {"old": 1} and len(scan.causal_uncertainty_modes) == 1


def test_zero_single_and_excess_family_score_contract():
    assert position.family_score([], {}, None, None, details=True) == (0.0, [])
    detail = dict(negative_twice_log_density=12.0)

    def evaluate(p, x, powers, entries, *, details, refine_phase):
        assert details == refine_phase
        return detail if details else 12.0

    family = SimpleNamespace(evaluate=evaluate)
    context = dict(powers={}, entries=[])
    assert position.family_score([family], context, None, None) == 12.0
    assert position.family_score([family], context, None, None, True) == (12.0, [detail])
    with pytest.raises(ValueError, match="two-family"):
        position.family_score([family] * 3, context, None, None)


def test_new_satellite_and_extended_prediction_do_not_change_calibration(monkeypatch):
    monkeypatch.setattr(position, "Satrec", SimpleNamespace(twoline2rv=lambda *a: object()))

    def propagate(catalogue, origin, times):
        count = len(catalogue.satellites)
        return (
            np.ones((count, len(times), 3)),
            np.ones((count, len(times), 3)),
            np.ones(count, bool),
        )

    # The propagation port is verified separately against SGP4; here exercise
    # catalogue append and the lifetime of the distinct predictive sky view.
    monkeypatch.setattr(position, "ecef_states", propagate)
    sky = dict(
        time_s=np.arange(3.0),
        position_km=np.zeros((1, 3, 3)),
        velocity_km_s=np.zeros((1, 3, 3)),
        phase_sigma_s=np.ones(1),
    )
    scan = SimpleNamespace(
        norads=np.array([1]),
        sky=sky,
        origin_utc_ns=123,
        elements={"1": dict(lines=["l1", "l2"])},
        causal_uncertainty_modes={"old": 1},
        tracks=[dict(observation_ids=["a", "b"], key="track")],
    )
    context = dict(scan=scan)
    entry = position.add_target(
        context,
        dict(track_index=0, source_local_indices=[0, 1], observation_ids=["a", "b"]),
        dict(norad=2, alias=0),
        dict(elements={"2": dict(lines=["l1", "l2"])}),
        [],
        {a: {} for a in ARMS},
    )
    assert entry["candidate_index"] == 1
    assert scan.norads.tolist() == [1] and list(scan.elements) == ["1"]
    assert scan.sky is sky and scan.sky["position_km"].shape == (1, 3, 3)
    candidate = context["scan"]
    assert candidate.norads.tolist() == [1, 2]
    assert position.prediction_scan(candidate, 15) is candidate
    predictive = position.prediction_scan(candidate, 30)
    assert predictive is not candidate
    assert predictive.sky["time_s"][[0, -1]].tolist() == [-40, 340]
    assert len(candidate.sky["time_s"]) == 3
    assert predictive.causal_uncertainty_modes == {}
    assert candidate.causal_uncertainty_modes == {"old": 1}
