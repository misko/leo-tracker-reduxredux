import numpy as np
import pytest

from held_precision_finish import FixedPrecision, replace_scales


def test_precision_replacement_keeps_anchor_and_does_not_compound_margin():
    original = np.array([60., 90., 102., 360.])
    targets = {"low": 2., "anchor": None, "high": 1e4, "direct": 150.}
    updated = replace_scales(original, list(targets), targets)
    assert updated.tolist() == [40., 90., 600., 150.]
    assert original.tolist() == [60., 90., 102., 360.]
    assert np.array_equal(updated, replace_scales(updated, list(targets), targets))


def test_missing_precision_rejects_fit_instead_of_dropping_rows():
    with pytest.raises(KeyError):
        replace_scales([45.], ["missing"], {})


def test_scope_restores_and_report_counts_caps_and_apertures():
    class Fit:
        fitted_c = False

    fit = FixedPrecision({"short_floor": 3., "short_cap": 700., "anchor": None})
    ids = list(fit.targets)
    with fit.stage("fit"):
        fit.record(Fit(), "curved", ids, [100., 90., 120.], [40., 600., 120.])
        with pytest.raises(ValueError, match="different measurement"):
            fit.record(Fit(), "curved", ["short_cap"], [90.], [599.])
    assert fit.phase is None
    report = fit.summary()["scopes"]["fit"]["c0"]["curved"]
    assert [report["8"]["floor_hits"], report["8"]["ceiling_hits"]] == [1, 1]
    assert report["20"]["changed"] == 0
