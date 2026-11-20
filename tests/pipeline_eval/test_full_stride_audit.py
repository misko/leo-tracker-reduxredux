import json
from hashlib import sha256

import pytest

from tools.pipeline_eval.qualification import full_stride_audit as audit


def test_an_in_flight_or_unreconciled_failure_cannot_be_sealed(tmp_path):
    lock = json.dumps({"cases": {"DS26-0162": {}}}).encode()
    (tmp_path / "source-lock.json").write_bytes(lock)
    (tmp_path / "source-lock.sha256").write_text(sha256(lock).hexdigest())
    case = tmp_path / "DS26-0162"
    for branch in audit.BRANCHES:
        (case / branch).mkdir(parents=True)
        (case / branch / "service-launch.json").touch()
    assert audit.pending(tmp_path) == ["DS26-0162/control", "DS26-0162/candidate"]
    (case / "control/service.json").write_text('{"exit_code": 0}')
    (case / "candidate/service.json").write_text('{"exit_code": 124}')
    assert len(audit.pending(tmp_path)) == 2
    (case / "control/end.json").touch()
    (case / "candidate-failure.json").touch()
    assert audit.pending(tmp_path) == []


def test_raw_deadline_uses_complete_detector_even_if_the_position_timed_out():
    results = audit.detector_stats(
        [
            (
                "complete",
                dict(
                    dual_calls=3,
                    within_20ms=2,
                    counts=dict(detector_cpu_s=0.052, positive_candidates=5),
                ),
            ),
            (
                "timed_out_after_detection",
                dict(
                    dual_calls=2,
                    within_20ms=2,
                    counts=dict(detector_cpu_s=0.029, positive_candidates=2),
                ),
            ),
            ("timed_out_during_detection", dict(wall_to_failure_s=360)),
        ]
    )
    assert results["complete_ids"] == ["complete", "timed_out_after_detection"]
    assert results["deadline_fraction"] == 0.8
    assert results["valid_dual_rx_calls"] == 5
    assert results["positives"] == 7
    assert results["mean_detector_cpu_ms"] == pytest.approx(16.2)


def test_adoption_counts_require_same_visits_and_both_arms_in_additional_panel():
    def panel(control_wins, candidate_wins, candidate_ids=None):
        def detector(met, ids):
            return dict(complete_ids=ids, valid_dual_rx_calls=400, wall_at_most_20_ms=met)

        return dict(
            services={
                "control": dict(detector=detector(220, ["x", "y"])),
                "candidate": dict(detector=detector(350, candidate_ids or ["x", "y"])),
            },
            position={
                arm: dict(control=dict(within_10pct=a), candidate=dict(within_10pct=b))
                for arm, a, b in zip(audit.ARMS, control_wins, candidate_wins, strict=True)
            },
        )

    matched = panel((2, 2), (3, 3))
    assert audit.criterion(matched, matched)["passes"]
    assert not audit.criterion(matched, panel((2, 2), (3, 1)))["passes"]
    unequal = panel((2, 2), (3, 3), ["x", "z"])
    assert not audit.criterion(unequal, matched)["deadline_fraction_improved"]


def test_secondary_endpoint_keeps_missing_primary_explicit_and_binds_original_native():
    request = dict.fromkeys(audit.REQUEST, "same-request")
    resource = dict.fromkeys(
        (*audit.check.NATIVE_FIELDS, "input_manifest_sha256", "detector_sha256", "dual_calls"),
        "same",
    )
    complete = dict(status="ok", arms={a: dict(latlon=[1.1, 2.2]) for a in audit.ARMS})
    timeout = dict(status="timed_out", arms={a: dict(latlon=None) for a in audit.ARMS})
    prior = dict(request, native_sha256="native", result=timeout)
    repeat = dict(request, native_sha256="native", result=complete)
    audit.prior_repeat(prior, resource, repeat, resource)
    comparison = audit.control_parity(audit.REPEAT_CASE, repeat, None, prior, None, repeat)
    for arm in audit.ARMS:
        assert comparison["primary_position"]["arms"][arm]["state"] == "missing_archive"
        assert comparison["deadline_repeat_position"]["arms"][arm]["exact"]
    with pytest.raises(ValueError, match="complete native primary"):
        audit.prior_repeat(prior, resource, dict(repeat, native_sha256="other"), resource)
