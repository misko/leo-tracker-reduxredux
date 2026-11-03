from types import SimpleNamespace

import numpy as np
import pytest
from all_visible_bank import (
    ExpandedScanData,
    _expand_parameters,
    _expanded_order,
    _screen_visible,
    _visibility_nodes,
)


def test_visibility_nodes_cover_timing_window_on_original_quarter_second_grid():
    nodes = np.arange(-20.0, 31.25, 0.25)
    selected = _visibility_nodes(np.array([0.1, 10.2]), nodes, timing_window_s=10.0)
    assert selected[0] == pytest.approx(-9.75)
    assert selected[-1] == pytest.approx(20.0)
    np.testing.assert_allclose(np.diff(selected), 0.25, rtol=0, atol=1e-12)


def test_visibility_screen_uses_union_over_observers_and_keeps_below_horizon_valid():
    catalogue = SimpleNamespace()
    receiver = np.array([6378.0, 0.0, 0.0])
    observers = [(receiver, np.array([1.0, 0.0, 0.0]))]

    def propagate(_catalogue, indices, _origin, nodes, _taus):
        position = np.empty((len(indices), 1, len(nodes), 3))
        for local, index in enumerate(indices):
            position[local, 0] = [7000.0 if index == 0 else 6000.0, 0.0, 0.0]
        return position, np.zeros_like(position), np.asarray(indices)

    visible, valid, maximum = _screen_visible(
        catalogue,
        np.array([0, 2]),
        1,
        np.array([0.0, 0.25]),
        observers,
        propagate,
        float("inf"),
    )
    assert visible == {0}
    assert valid == {0, 2}
    assert maximum[0] == pytest.approx(1.0)
    assert maximum[2] == pytest.approx(-1.0)


def test_expanded_order_retains_old_order_then_adds_visible_catalogue_order():
    catalogue_numbers = np.array([300, 100, 200, 400])
    order = _expanded_order(
        np.array([200, 300]),
        catalogue_numbers,
        {0, 1, 3},
        {0, 1, 2, 3},
    )
    np.testing.assert_array_equal(order, [2, 0, 1, 3])
    np.testing.assert_array_equal(catalogue_numbers[order], [200, 300, 100, 400])


def test_expanded_order_rejects_missing_or_unpropagated_original_candidate():
    with pytest.raises(ValueError, match="absent"):
        _expanded_order(np.array([9]), np.array([1, 2]), {0}, {0, 1})
    with pytest.raises(ValueError, match="complete ephemeris"):
        _expanded_order(np.array([2]), np.array([1, 2]), {0}, {0})


def test_parameter_expansion_preserves_shared_and_remaps_old_timing():
    source = np.arange(10.0)
    expanded = _expand_parameters(source, np.array([2, 0, 3, 1]), 6)
    np.testing.assert_array_equal(expanded[:6], source[:6])
    np.testing.assert_array_equal(expanded[6:], [7.0, 9.0, 6.0, 8.0, 0.0, 0.0])


def test_expanded_data_is_timing_objective_compatible_and_remaps_indices():
    count = 65
    source = SimpleNamespace(
        times=np.array([0.0]),
        measured=np.array([0.0]),
        rf=np.array([12.0e9]),
        receiver=np.array([0]),
        channel=np.array([1]),
        group=np.array([0]),
        margin=np.array([1.0]),
        reference_time_s=150.0,
    )
    nodes = np.array([-0.25, 0.0, 0.25])
    position = np.zeros((count, len(nodes), 3))
    position[..., 0] = 7000.0
    arrays = {
        "nodes": nodes,
        "numbers": np.arange(1000, 1000 + count),
        "position": position,
        "velocity": np.zeros_like(position),
        "initial": np.zeros(6 + count),
        "old_numbers": np.array([1001, 1000]),
        "old_to_expanded": np.array([1, 0]),
        "maximum_elevation_sine": np.ones(count),
        "screen_visible": np.ones(count, dtype=bool),
        "retained_original": np.r_[np.ones(2, dtype=bool), np.zeros(count - 2, dtype=bool)],
    }
    data = ExpandedScanData(source, arrays, {"session_id": "scan"})
    np.testing.assert_array_equal(data.remap_satellites([1, 0]), [0, 1])
    parameters = data.expand_parameters(np.r_[np.zeros(6), [3.0, 4.0]])
    np.testing.assert_array_equal(parameters[6:8], [4.0, 3.0])
    predicted, visible = data.predict(data.initial, rows=np.array([0]), satellites=np.array([0]))
    assert predicted.shape == visible.shape == (1,)
    assert visible.dtype == np.bool_


def test_expanded_data_rejects_a_bank_that_does_not_expand_past_64():
    source = SimpleNamespace(**{
        name: np.array([0.0]) for name in ("times", "measured", "rf", "margin")
    })
    source.receiver = source.channel = source.group = np.array([0])
    arrays = {
        "nodes": np.array([0.0, 0.25]),
        "numbers": np.arange(64),
        "position": np.zeros((64, 2, 3)),
        "velocity": np.zeros((64, 2, 3)),
        "initial": np.zeros(70),
        "old_numbers": np.arange(64),
        "old_to_expanded": np.arange(64),
        "maximum_elevation_sine": np.zeros(64),
        "screen_visible": np.ones(64, dtype=bool),
        "retained_original": np.ones(64, dtype=bool),
    }
    with pytest.raises(ValueError, match="inconsistent dimensions"):
        ExpandedScanData(source, arrays, {"session_id": "scan"})
