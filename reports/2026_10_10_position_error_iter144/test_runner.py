from types import SimpleNamespace

import numpy as np
import pytest
from runner import audit_member, choose_snapshot, prepare_arm


@pytest.mark.parametrize("fail_second", [False, True])
def test_full_audit_same_source_and_partial_failure(monkeypatch, fail_second):
    import runner

    original = SimpleNamespace(digest="original")
    monkeypatch.setattr(runner, "record_pairs", lambda payload: {1: ("a", "b")})
    monkeypatch.setattr(
        runner, "choose_snapshot", lambda *a: (original, "payload", {"selected": "original"})
    )
    model = SimpleNamespace(
        size=9,
        initial_clock=np.zeros(1),
        basis=np.ones((1, 1)),
        bank=SimpleNamespace(numbers=np.array([1]), nodes_s=np.array([0.0, 1.0])),
        observations=SimpleNamespace(times_s=np.array([0.0, 1.0])),
        prior=None,
        score=SimpleNamespace(detection_budget=0.5, clutter_rate=0.1),
    )

    def construct(model, endpoint, arm):
        return dict(
            spatial=np.zeros((2, 2)),
            nuisance=np.zeros((2, 1)),
            weights=np.ones(2),
            full_jacobian=np.zeros((2, 1, 3)),
            observations=2,
            satellites=1,
            objective_delta=0.0,
        )

    calls = []

    def projected(*args, **kwargs):
        calls.append(1)
        if fail_second and len(calls) == 2:
            raise ValueError("second arm failure")
        assert np.array_equal(args[0], np.zeros(2))
        return {"total_energy": 0.0}

    progress = {}
    kwargs = dict(
        propagate=lambda *a: (np.zeros((1, 1, 2, 3)), np.zeros((1, 1, 2, 3)), [0]),
        parse_catalogue=lambda p: SimpleNamespace(satellite_numbers=np.array([1])),
        bank_type=lambda *a: object(),
        predictor=lambda *a, **kw: (np.ones((2, 1)), np.ones((2, 1), bool), None, None),
        progress=progress,
    )
    args = (
        model,
        {
            "prepared": SimpleNamespace(start_utc_ns=0),
            "model_identity": {"snapshot_sha256": "original"},
        },
        {arm: {"vector": np.zeros(9)} for arm in ("fitted-c", "zero-c")},
        SimpleNamespace(select_latest_before=lambda t: original, read=lambda r: "payload"),
        SimpleNamespace(construct=construct),
        projected,
    )
    if fail_second:
        with pytest.raises(ValueError, match="second arm"):
            audit_member(*args, **kwargs)
        assert list(progress["arms"]) == ["fitted-c"]
    else:
        result = audit_member(*args, **kwargs)
        assert set(result["arms"]) == {"fitted-c", "zero-c"}
        for arm in result["arms"].values():
            assert arm["prediction_delta_rms_hz"] == arm["event_normalizer_nll_delta"] == 0.0
    assert all(row["status"] == "complete" for row in progress["admissions"].values())


def ref(i):
    return SimpleNamespace(
        provider="p", collected_utc_ns=100000000000000 - i, sha256=str(i), byte_size=1
    )


def test_public_fetch_cap_counts_read_parse_failures():
    calls = []

    class Reader:
        def list_snapshots(self, provider):
            assert provider == "p"
            return [ref(i) for i in range(1, 30)]

        def read(self, item):
            calls.append(item.sha256)
            raise ValueError("read failed")

    selected, payload, receipt = choose_snapshot(
        Reader(), ref(0), {1: ("a", "b")}, [1], lambda p: {}
    )
    assert selected is payload is None
    assert len(calls) == len(receipt["inspected"]) == 10


def test_resource_guard_prevents_adapter_allocation():
    model = SimpleNamespace(
        size=1000,
        initial_clock=np.zeros(1000),
        observations=SimpleNamespace(times_s=np.empty(100000)),
        bank=SimpleNamespace(numbers=np.empty(1000)),
    )
    adapter = SimpleNamespace(construct=lambda *a: pytest.fail("No allocation on resource failure"))
    with pytest.raises(MemoryError):
        prepare_arm(model, {}, "fitted-c", adapter)


def test_both_ordinary_arms_admitted_before_any_catalogue_access():
    calls = []
    model = SimpleNamespace(
        size=8,
        initial_clock=np.zeros(2),
        observations=SimpleNamespace(times_s=np.zeros(2)),
        bank=SimpleNamespace(numbers=np.array([1])),
    )

    def construct(model, endpoint, arm):
        calls.append(arm)
        if arm == "zero-c":
            raise ValueError("saved objective mismatch")
        return dict(spatial=np.zeros((2, 2)), full_jacobian=np.zeros((2, 1, 10)))

    class Reader:
        def select_latest_before(self, *a):
            pytest.fail("Catalogue cannot open before both arms pass")

    with pytest.raises(ValueError, match="objective mismatch"):
        audit_member(
            model,
            {},
            {"fitted-c": {}, "zero-c": {}},
            Reader(),
            SimpleNamespace(construct=construct),
            None,
            propagate=None,
            parse_catalogue=None,
            bank_type=None,
            predictor=None,
        )
    assert calls == ["fitted-c", "zero-c"]


def test_real_public_text_reader_selection_and_same_source_geometry(tmp_path):
    from runner import record_pairs

    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from leo.analysis.hard60_score import predict_orbits
    from leo.contracts.regional_position import PositionOrbitBank
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import element_line_checksum, parse_element_sets
    from tests.analysis.test_hard60_joint import setup
    from tests.operations.test_tle_archive import ELEMENT_SET, _store

    lines = ELEMENT_SET.splitlines()
    changed = lines[2].replace("172.0234", "173.0234")
    changed = changed[:-1] + str(element_line_checksum(changed))
    older_payload = "\n".join([lines[0], lines[1], changed]) + "\n"
    original = _store(tmp_path, "space-track", 100000000000000, ELEMENT_SET)
    _store(tmp_path, "space-track", 99999999999999, older_payload)
    reader = TleArchiveReader(tmp_path)
    assert isinstance(reader.read(original), str)
    selected, payload, receipt = choose_snapshot(
        reader, original, record_pairs(ELEMENT_SET), [44714], record_pairs
    )
    assert selected is not None and isinstance(payload, str)
    assert receipt["inspected"][0]["candidates"]["changed"] == [44714]
    with pytest.raises(ValueError, match="Duplicate"):
        record_pairs(ELEMENT_SET + ELEMENT_SET)
    catalogue = parse_element_sets(ELEMENT_SET)
    base, _ = setup()
    origin = catalogue.element_epoch_utc_ns()[0]
    nodes = np.arange(
        np.floor(base.observations.times_s.min()) - 21,
        np.ceil(base.observations.times_s.max()) + 21.25,
        0.25,
    )
    position, velocity, valid = propagate_candidate_states(
        catalogue, [0], origin, nodes, np.array([0.0])
    )
    assert valid.tolist() == [0]
    bank = PositionOrbitBank(np.array([44714]), nodes, position[:, 0], velocity[:, 0])
    second = propagate_candidate_states(catalogue, [0], origin, nodes, np.array([0.0]))
    other = PositionOrbitBank(np.array([44714]), nodes, second[0][:, 0], second[1][:, 0])
    first_prediction = predict_orbits(
        bank, base.observations, base.prior, [0, 0], np.array([0.0]), derivatives=False
    )
    second_prediction = predict_orbits(
        other, base.observations, base.prior, [0, 0], np.array([0.0]), derivatives=False
    )
    assert len(first_prediction) == 4
    np.testing.assert_array_equal(first_prediction[0], second_prediction[0])
    np.testing.assert_array_equal(first_prediction[1], second_prediction[1])
