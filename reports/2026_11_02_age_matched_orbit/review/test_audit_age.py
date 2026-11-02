"""Independent audit checks on causal pairing and conservative covariance."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location("age_receipt_audit_tested", Path(__file__).with_name("audit_age.py"))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def version(epoch_hours, collection_hours, suffix):
    return dict(epoch=int(epoch_hours * 3.6e12), collected_utc_ns=int(collection_hours * 3.6e12), lines=[suffix, suffix])


def test_covariance_keeps_floor_and_caps_large_revision_without_mean_shift():
    a = np.array([[100., 0., 0.], [100., 0., 0.]])
    second, covariance = audit.bounded_covariance(a)
    assert second[0, 0] == 10000.
    np.testing.assert_allclose(covariance, np.diag([16., 1., 1.]))
    # Centering these equal revisions would erase their uncertainty contribution.
    _, centered = audit.bounded_covariance(a - a.mean(axis=0))
    np.testing.assert_allclose(centered, np.eye(3))


def test_covariance_rejects_nonfinite_and_wrong_coordinates():
    for bad in ([[np.nan, 0., 0.]], [[1., 2.]], []):
        with pytest.raises(ValueError, match="Invalid physical coefficients"):
            audit.bounded_covariance(bad)


def test_maximum_matching_does_not_reuse_or_greedily_consume_revisions():
    rows = [version(h, h + 1, str(h)) for h in (1, 9, 11, 21)]
    pairs = audit.independent_pairs(rows, int(21 * 3.6e12), int(24 * 3.6e12), 10.)
    assert len(pairs) == 2
    epochs = [r["epoch"] for pair in pairs for r in pair]
    assert len(set(epochs)) == 4


def test_forecast_availability_and_earliest_collection_are_mandatory():
    older = version(1, 15, "old-late")
    newer = version(11, 12, "new")
    assert audit.independent_pairs([older, newer], int(11 * 3.6e12), int(24 * 3.6e12), 10.) == []
    available = version(1, 2, "old-early")
    pairs = audit.independent_pairs([older, available, newer], int(11 * 3.6e12), int(24 * 3.6e12), 10.)
    assert pairs == [(available, newer)]
