"""Check that a history-selected empty is not silently counted as a native miss."""

import pytest

from reports.ALGO08.v3.south_empty_graph_arrival import WINDOWS, aperture_accounting, score_group


def test_history_erasure_and_native_empty_are_accounted_by_aperture():
    rows = {"s1": dict(short=True, factor={}), "s2": dict(short=True, factor=None),
            "s3": dict(short=True, factor=None), "a1": dict(short=False, factor=None)}
    audit = dict(native_calls=dict(short_primary=3, full=1), factors=dict(short_primary=2, full=1))
    held = dict(choice=dict(route="history"), refinement_calls=0, observed=3, selected=1)
    assert aperture_accounting(rows, audit, held) == {
        "short_primary": dict(calls=3, native_positives=2, selected_positives=1,
                              native_empty=1, erased_by_history=1, selected_empty=2),
        "full": dict(calls=1, native_positives=1, selected_positives=0,
                     native_empty=0, erased_by_history=1, selected_empty=1)}


def test_selector_receipt_with_native_counts_outside_call_scope_is_rejected():
    rows = {"s1": dict(short=True, factor=None)}
    audit = dict(native_calls=dict(short_primary=1), factors=dict(short_primary=2))
    held = dict(choice=dict(route="history"), refinement_calls=0, observed=2, selected=0)
    with pytest.raises(ValueError, match="Impossible"):
        aperture_accounting(rows, audit, held)


def test_zero_prediction_scope_keeps_every_window_and_control_explicit():
    observed = {"miss": dict(factor={}), "empty": dict(factor=None)}
    score = score_group(set(observed), {}, observed)
    assert score["installed_positive_denominator"] == 1 and score["installed_positive_queries"] == 0
    assert score["windows"].keys() == WINDOWS.keys()
    assert all(names == dict(carrier_only=0, interpolated=0, left_only=0, quarter_period_control=0)
               for names in score["windows"].values())
