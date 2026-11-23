from copy import deepcopy
from pathlib import Path

import pytest


@pytest.fixture
def replay(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    import aperture_factor_position

    return aperture_factor_position


@pytest.fixture
def measured(replay):
    full, prefix, centered = [0, 100, -0.2, -225., 0.5, 0.1], [0, 101, -0.3, -400., 0.6, 0.3], [0, 102, 0.4, 300., 0.7, 0.2]
    rows, enrollment, index = [], [], {}
    for visit in range(2):
        index[visit] = dict(iq_sha256=f"sha256:{visit}", acquisition=dict(sample_start=100 + visit))
        for lane in range(2):
            mode = "full" if visit == 0 else "short_primary"
            before = [full] if visit == 0 else [prefix] if lane == 0 else []
            after = [full] if visit == 0 else [centered]
            metadata = dict(visit_index=visit, receiver_id=lane, edge="lower", channel=1,
                            actual_rf_hz=10.7e9, valid_start_counter=100 + visit)
            rows.append(dict(metadata, candidates=replay.from_factors(before)))
            enrollment.append(dict(metadata=metadata, lane=lane, key=f"DS30-0008:{visit}", mode=mode,
                                   iq_sha256=f"sha256:{visit}", prefix=before, centered=after,
                                   installed=[full] if visit == 0 else []))
    return rows, enrollment, index


def test_complete_tuple_and_empty_state_replacement_keep_anchors_and_metadata(replay, measured):
    rows, enrollment, index = measured
    candidate, manifest, modes = replay.replace(rows, enrollment, index)
    assert candidate[:2] == rows[:2]
    assert all(replay.metadata(a) == replay.metadata(b) for a, b in zip(rows, candidate))
    assert candidate[2]["candidates"] == candidate[3]["candidates"] == replay.from_factors(enrollment[2]["centered"])
    stats = replay.differences(rows, candidate, modes, len(enrollment))["counts"]
    assert stats["enrolled_primary"] == dict(opportunities=2, prefix_present=1, centered_present=2,
                                              changed_factor=1, added=1)
    assert len(manifest) == 2


@pytest.mark.parametrize(("index", "field", "value", "reason"), [
    (2, "iq_sha256", "sha256:wrong", "signed stereo"),
    (2, "prefix", [], "complete native prefix"),
    (0, "centered", [], "unchanged native anchor"),
    (3, "centered", [[1, 102, 0.4, 300., 0.7, 0.2]], "native rank zero"),
])
def test_bound_joins_reject_different_iq_or_partial_factor(replay, measured, index, field, value, reason):
    rows, enrollment, windows = deepcopy(measured)
    enrollment[index][field] = value
    with pytest.raises(ValueError, match=reason):
        replay.replace(rows, enrollment, windows)


def test_full_chronology_can_change_later_selection_with_equal_raw_factors(replay):
    row = dict(receiver_id=0, channel=1, actual_rf_hz=10.7e9)
    factor = replay.from_factors([[0, 100, 0., -3000., 0.6, 0.2]])
    before = [dict(row, valid_start_counter=10_000_000 * (i + 1), candidates=factor) for i in range(4)]
    raw = dict(source=dict(probes=before, raw_recording_authority_digest="sha256:" + "0" * 64),
               provenance=dict(detector_sha256="sha256:" + "1" * 64))
    candidate = replay.rebound(raw, [dict(before[0], candidates=[]), *before[1:]], ["counterfactual"])
    first, second = (replay.continued(packet)["source"]["probes"] for packet in (raw, candidate))
    changes = replay.differences(first, second, ["short_primary"] * 3 + ["full"], 1)
    assert len(changes["changes"]) == 1
    assert changes["counts"]["later_anchor"] == dict(opportunities=1, prefix_present=1, centered_present=0, lost=1)


def test_reference_grid_parity_ignores_only_the_independent_clock(replay):
    grid = dict(binding="signed", elapsed_seconds=15., points=[2.])
    other = dict(grid, elapsed_seconds=17.)
    assert replay.grid_without_elapsed(grid) == replay.grid_without_elapsed(other)
    assert replay.grid_without_elapsed(grid) != replay.grid_without_elapsed(dict(other, points=[3.]))


def test_signed_rf_and_position_deltas_remain_separate_per_calibration_arm(replay):
    prefix = dict(terminal=dict(arms={"c0": dict(latlon=[2., 3.], rf_rms_hz=8.),
                                      "fitted_c": dict(latlon=[2., 4.], rf_rms_hz=7.)}),
                  horizontal_error_km={"c0": 2., "fitted_c": 4.})
    centered = deepcopy(prefix)
    centered["terminal"]["arms"]["fitted_c"]["rf_rms_hz"] = 6.
    centered["horizontal_error_km"]["fitted_c"] = 5.
    changes = replay.compare_endpoints(prefix, centered)
    assert changes["fitted_c"] == dict(shift_km=0., horizontal_error_delta_km=1., rf_rms_delta_hz=-1.)
    assert changes["c0"] == dict(shift_km=0., horizontal_error_delta_km=0., rf_rms_delta_hz=0.)
