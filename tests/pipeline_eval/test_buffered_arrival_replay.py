import pytest

from tools.pipeline_eval.qualification import buffered_arrival_replay as trial
from tools.pipeline_eval.qualification import buffered_arrival_results as results


def fixture():
    events = [
        dict(
            visit=i,
            full_visit_sha256=f"event-{i}",
            sample_start=i * 100,
            sample_end=i * 100 + 99,
            status=status,
        )
        for i, status in enumerate(("processed", "invalid_capture", "processed"))
    ]
    doc = {
        "source": {"probes": [dict(visit_index=i, receiver_id=rx) for i in (0, 2) for rx in (0, 1)]}
    }
    rows = [
        dict(e, outcome=outcome)
        for e, outcome in zip(
            events,
            ("emitted", "invalid_capture", "emitted"),
            strict=True,
        )
    ]
    return rows, events, doc


def test_capacity_override_restores_previously_published_configuration():
    assert trial.paced.WAITING == 1
    existing = trial.paced.MODULE
    with trial.config():
        assert trial.paced.WAITING == 4
        assert trial.paced.MODULE == trial.MODULE
    assert trial.paced.WAITING == 1 and existing == trial.paced.MODULE


def test_complete_byte_verified_probes_can_reuse_exact_input_fit():
    rows, events, doc = fixture()
    drops, count, fingerprint = results.support(rows, events, doc)
    assert (drops, count) == ([], 4)
    assert fingerprint == trial.paced.fingerprint([(0, 0), (0, 1), (2, 0), (2, 1)])
    rows[2]["outcome"] = "queue_drop"
    assert results.support(rows, events, doc)[:2] == ([2], 2)


def test_digest_or_hardware_validity_disagreement_rejects_reuse():
    rows, events, doc = fixture()
    rows[1]["outcome"] = "queue_drop"
    with pytest.raises(ValueError, match="capture validity"):
        results.support(rows, events, doc)
    rows, events, doc = fixture()
    rows[2]["full_visit_sha256"] = "different"
    with pytest.raises(ValueError, match="unbound"):
        results.support(rows, events, doc)


def test_drop_identity_changes_are_reported_separately():
    shared = dict(
        id="case",
        mode="candidate",
        sample_start=5,
        sample_end=9,
        arrival_ns=0,
        outcome="queue_drop",
    )
    a, b, both = (dict(shared, visit=i) for i in range(3))
    rows = results.compare_drops([a, both], [b, both])
    assert [(x["visit"], x["one_slot_drop"], x["four_slot_drop"]) for x in rows] == [
        (0, True, False),
        (1, False, True),
        (2, True, True),
    ]
