import numpy as np
import pytest

from leo.analysis.localization_v3 import retained_position as model
from tests.analysis.test_localization_v3_position import prepared


def test_causal_widths_use_explicit_epoch_provenance_and_preserve_fallback(monkeypatch):
    scan, _ = prepared()
    scan.norads = np.array([10, 20])
    scan.origin_utc_ns = 50_000_000_000
    scan.elements = {str(j): dict(provenance=dict(element_epoch_utc_ns=30_000_000_000))
                     for j in scan.norads}
    scan.previous_sources = {'10': dict(epoch_utc_ns=20_000_000_000)}
    monkeypatch.setattr(model, 'previous_bank', lambda *a: ({}, {}, {10: 2.}))
    widths, receipt = model.phase_widths(scan, [0, 1])
    np.testing.assert_array_equal(widths, [np.hypot(1., 4.), 1.])
    assert receipt[0] == dict(norad=10, age_s=20., previous_epoch_gap_s=10.,
                              old_new_alignment_s=2., sigma_s=np.hypot(1., 4.))
    assert receipt[1]['old_new_alignment_s'] is None
    scan.previous_sources = None
    with pytest.raises(ValueError, match='provenance'):
        model.phase_widths(scan, [0])


def test_retained_fit_preserves_mask_and_absolute_phase_prior_in_both_arms():
    scan, node = prepared()
    scan.previous_sources = {}
    scan.elements = {'99999': dict(provenance=dict(element_epoch_utc_ns=0))}
    keep = np.ones(41, bool)
    keep[:12] = False
    records = []
    for arm in ('c0', 'fitted_c'):
        p, record = model.fit_position(scan, node, keep, [], arm, 'native',
                                       rounds=2, iterations=1)
        assert record['active_points'] == 29
        assert record['phase_rounds'] == 2 and record['scales'] == {}
        assert record['tracks'][0]['points'] == 29
        assert len(record['tracks'][0]['observation_ids']) == 41  # Design is intact.
        np.testing.assert_array_equal(p.phase_sigma, [1.])
        np.testing.assert_array_equal(record['history'][0]['phase_reference'], [0.])
        records.append(record)
    assert records[0]['aliases'] == records[1]['aliases']
    np.testing.assert_array_equal(keep, np.r_[np.zeros(12, bool), np.ones(29, bool)])


def test_repaired_unit_fit_keeps_original_bank_widths_and_separate_causal_receipt(monkeypatch):
    scan, node = prepared()
    scan.sky['phase_sigma_s'][:] = 2.
    monkeypatch.setattr(model, 'phase_widths', lambda *a: (np.array([7.]), ['causal']))
    p, _, history, receipt = model.repaired_fit(scan, node, 'c0', 'unit',
                                               np.ones(41, bool), rounds=2, iterations=1)
    np.testing.assert_array_equal(p.phase_sigma, [2.])
    assert len(history) == 2 and receipt == ['causal']
    with pytest.raises(ValueError, match='prior'):
        model.repaired_fit(scan, node, 'c0', 'tail4', np.ones(41, bool))


def test_optional_scale_columns_do_not_change_native_default_design():
    scan, node = prepared()
    native = model.PositionNormal(scan, node, 150., False)
    ignored = model.PositionNormal(scan, node, 150., False, scale_labels=[99])
    expanded = model.PositionNormal(scan, node, 150., False, scale_labels=[0])
    a, b, c = (p.calculate(np.zeros(2)) for p in (native, ignored, expanded))
    np.testing.assert_array_equal(a['features'], b['features'])
    np.testing.assert_array_equal(a['coefficient'], b['coefficient'])
    assert c['features'].shape[1] == a['features'].shape[1]+1
    assert expanded.scale_state(np.zeros(2)).shape == (1,)
    assert native.scale_state(np.zeros(2)).shape == (0,)
