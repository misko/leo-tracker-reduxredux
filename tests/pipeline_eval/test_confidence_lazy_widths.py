from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


HERE = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
LINES = (
    "1 25544U 98067A   23073.02771182  .00017654  00000-0  32060-3 0  999",
    "2 25544  51.6427 244.1570 0006419  42.2167  74.9388 15.4995423538707",
)


@pytest.fixture
def load(monkeypatch):
    monkeypatch.syspath_prepend(str(HERE))
    import confidence_lazy_widths as lazy
    import lighter_joint_estimator as estimator
    from leo.analysis.localization_v3 import orbit_modes as modes
    from leo.sky.propagation import element_line_checksum, parse_element_sets

    # In-memory records exercise the installed parser and both real SGP4 passes.
    rows = [source.replace("25544", str(norad)) for norad in (25544, 25545) for source in LINES]
    text = "".join(f"{line}{element_line_checksum(line)}\n" for line in rows)
    earlier = parse_element_sets(text)
    epoch = earlier.element_epoch_utc_ns()[0]
    origin = int(datetime(2023, 3, 14, 12, tzinfo=UTC).timestamp())*10**9
    times = np.arange(-17., 318.)
    position, velocity, usable = modes.ecef_states(earlier, origin, times+0.75)
    assert usable.all()
    norads = np.array([25545, 25546, 25544])
    elements = {str(n): {"provenance": {"element_epoch_utc_ns": epoch+int(n-25543)*10**9}}
                for n in norads}
    scan = SimpleNamespace(origin_utc_ns=origin, previous_tle=text,
                           previous_tle_sha256=sha256(text.encode()).hexdigest(),
                           sky=dict(time_s=times, position_km=position[[1, 0, 0]],
                                    velocity_km_s=velocity[[1, 0, 0]]),
                           norads=norads, elements=elements,
                           previous_sources={str(n): {"epoch_utc_ns": epoch} for n in (25544, 25545)})
    return lazy, estimator, modes, scan


def test_full_width_bits_order_and_original_propagation_control(monkeypatch, load):
    lazy, estimator, modes, scan = load
    original = estimator.phase_widths
    labels = [0, 1, 2]
    control = deepcopy(scan)
    calls = []
    propagate = modes.ecef_states

    def counted(catalogue, origin, times):
        calls.append((catalogue.satellite_numbers, len(times)))
        return propagate(catalogue, origin, times)

    monkeypatch.setattr(modes, "ecef_states", counted)
    expected, receipts = original(control, labels)
    ordinary = list(calls)
    assert ordinary[0] == ((25545, 25544), 3)
    assert len(ordinary) == 2 and ordinary[1][1] >= 371
    calls.clear()
    audit = Counter()
    with lazy.binding(estimator, audit):
        for _ in range(2):
            actual, actual_receipts = estimator.phase_widths(scan, labels)
            assert actual.tobytes() == expected.tobytes()
            assert actual_receipts == receipts
        assert calls == ordinary
        assert audit["width_alignment_hits"] == 1
        assert label_order(actual_receipts) == [25545, 25546, 25544]
        assert actual_receipts[1]["old_new_alignment_s"] is None and actual[1] == 1.0
        assert not scan.previous_shape_cache
        assert audit["alignment_labels"] == 2
        assert audit["interior_shift_cells_elided"] == 2*(335-2)
        assert audit["padded_propagation_cells"] == 2*ordinary[1][1]
        # An independent full-bank caller still constructs its original states,
        # and its result is exactly the eager control's complete earlier bank.
        full, available, alignments = modes.previous_bank(scan, labels)
        expected_bank, ordinary_available, ordinary_alignments = modes.previous_bank(control, labels)
        assert calls == ordinary*2
        assert available == ordinary_available and alignments == ordinary_alignments
        assert all(full[k].tobytes() == expected_bank[k].tobytes() for k in full)
    assert estimator.phase_widths is original


def label_order(receipts):
    return [row["norad"] for row in receipts]


@pytest.mark.parametrize("health", ("padded_status", "padded_nonfinite", "alignment_status", "digest"))
def test_original_failures_survive_width_only_entry(monkeypatch, load, health):
    lazy, estimator, modes, scan = load
    propagate = modes.ecef_states
    calls = []

    def faulty(catalogue, origin, times):
        position, velocity, good = propagate(catalogue, origin, times)
        calls.append(len(times))
        if (len(times) == 3) == (health == "alignment_status") and health != "digest":
            if health == "padded_nonfinite":
                position[0, len(times)//2, 0] = np.nan
            else:
                good[0] = False
        return position, velocity, good

    monkeypatch.setattr(modes, "ecef_states", faulty)
    if health == "digest":
        scan.previous_tle += "\n"
    error = ValueError if health in ("padded_nonfinite", "digest") else AssertionError
    with pytest.raises(error) as expected:
        estimator.phase_widths(deepcopy(scan), [0, 1, 2])
    original_calls = list(calls)
    calls.clear()
    audit = Counter()
    with lazy.binding(estimator, audit), pytest.raises(error) as received:
        estimator.phase_widths(scan, [0, 1, 2])
    assert str(received.value) == str(expected.value)
    assert calls == original_calls*2
    assert audit["original_replay_after_guard_error"] == 1
    assert audit["interior_shift_cells_elided"] == 0


def test_mutable_bank_and_unsupported_layout_cannot_take_a_stale_alignment(load):
    lazy, estimator, _, scan = load
    original = estimator.phase_widths
    audit = Counter()
    with lazy.binding(estimator, audit):
        estimator.phase_widths(scan, [0, 1, 2])
        scan.sky["position_km"][0, 100, 2] += 2
        actual, _ = estimator.phase_widths(scan, [0, 1, 2])
        reference, _ = original(deepcopy(scan), [0, 1, 2])
        assert actual.tobytes() == reference.tobytes()
        actual_subset, _ = estimator.phase_widths(scan, [2, 0])
        expected_subset, _ = original(deepcopy(scan), [2, 0])
        assert actual_subset.tobytes() == expected_subset.tobytes()
    assert audit["padded_health_checked"] == 2
    assert audit["width_alignment_hits"] == 0
    assert (2, 0) in scan.previous_shape_cache


def test_real_named_history_wrapper_still_recovers_three_sample_failure(monkeypatch, load):
    lazy, estimator, modes, scan = load
    from leo.analysis.localization_v3 import retained_position as retained
    from named_history_once import recover_previous

    propagate = modes.ecef_states

    def faulty(catalogue, origin, times):
        p, v, good = propagate(catalogue, origin, times)
        if len(times) == 3 and 25545 in catalogue.satellite_numbers:
            good[catalogue.satellite_numbers.index(25545)] = False
        return p, v, good

    def subset(catalogue, indices):
        return type(catalogue)(*(tuple(getattr(catalogue, name)[i] for i in indices)
                                 for name in ("names", "satellite_numbers", "satellites")))

    monkeypatch.setattr(modes, "ecef_states", faulty)
    labels = [0, 1, 2]
    expected_history, history = [], []
    with recover_previous(modes, retained, subset, expected_history):
        expected, receipts = estimator.phase_widths(deepcopy(scan), labels)
    audit = Counter()
    with lazy.binding(estimator, audit), recover_previous(modes, retained, subset, history):
        actual, actual_receipts = estimator.phase_widths(scan, labels)
    assert actual.tobytes() == expected.tobytes()
    assert actual_receipts == receipts
    assert [row["failed_previous_norads"] for row in history] == [row["failed_previous_norads"]
                                                                 for row in expected_history] == [[25545]]
    assert audit["original_replay_after_guard_error"] == 1
    assert audit["interior_shift_cells_elided"] == 0


def test_original_confidence_entry_preserves_all_candidate_scores(monkeypatch, load):
    lazy, estimator, _, scan = load
    times = np.arange(33.)
    scan.times = times
    scan.tracks = [dict(key=str(i), times=times, values=200*np.cos(times/9.+i), receiver=1,
                        channel=i+1, rf_hz=(114+i)*1e8) for i in range(2)]
    scan.hardware = lambda track, beta: np.zeros(len(track["times"]))
    scan.rx_basis = [np.zeros((len(times), 1))]*2
    scan.radio_sigma_hz = 150.
    xyz = scan.sky["position_km"][0, 17]
    lat, lon = np.rad2deg((np.arctan2(xyz[2], np.hypot(*xyz[:2])), np.arctan2(xyz[1], xyz[0])))
    scan.search_region = SimpleNamespace(half_width_km=10., latlon=lambda point: (lat+point[0]/100., lon+point[1]/100.))
    node = dict(seed=dict(rows=[dict(component=str(i), active_curvature=True, candidate_index=0) for i in range(2)]))
    baseline = {"arms": {"c0": {"record": dict(phase_reference=np.zeros(1), endpoint_east_north_km=np.zeros(2))}}}
    monkeypatch.setattr(estimator, "problem", lambda *_: SimpleNamespace(
        state=lambda _: dict(beta=np.zeros(1), smooth=[np.zeros(1)]*2)))
    labels = []
    profile = estimator.family_weighting.candidate_profile

    def read_profile(y, f, derivative, elevation, sigma, widths):
        labels.append(len(widths))
        return profile(y, f, derivative, elevation, sigma, widths)

    monkeypatch.setattr(estimator.family_weighting, "candidate_profile", read_profile)
    keep = np.ones(2*len(times), bool)
    expected = estimator.minimum_confidence(deepcopy(scan), node, keep, baseline, receipts=[])
    audit = Counter()
    with lazy.binding(estimator, audit):
        actual = estimator.minimum_confidence(scan, node, keep, baseline, receipts=[])
    assert np.isfinite(actual).all() and actual.tobytes() == expected.tobytes()
    assert labels == [3]*20
    assert audit["padded_health_checked"] == 1
