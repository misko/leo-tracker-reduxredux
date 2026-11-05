import numpy as np
import pytest

from leo.analysis.localization_v3 import reassociation_catalogue as catalogue


@pytest.mark.parametrize(
    "codes,expected",
    [
        ([0, 0], "eligible"),
        ([6, 6], "exclude_consistent_model_invalid_all_grid"),
        ([0, 6], "block_partial_grid_failure"),
        ([1, 6], "block_unknown_or_inconsistent_all_grid_failure"),
        ([5, 5], "block_unknown_or_inconsistent_all_grid_failure"),
    ],
)
def test_propagation_classes_do_not_hide_partial_or_unknown_failures(codes, expected):
    assert catalogue.classify(codes, np.ones((2, 3)), np.ones((2, 3))) == expected


def test_error_free_nonfinite_orbits_block_catalogue():
    positions = np.ones((2, 3))
    positions[1, 0] = np.nan
    assert catalogue.classify([0, 0], positions, np.ones((2, 3))) == "block_nonfinite_without_error"


@pytest.mark.parametrize("epoch,collection", [(1, 0), (-73 * 3.6e12, 0), (0, 1)])
def test_noncausal_or_expired_catalogue_is_rejected_before_propagation(
    monkeypatch, epoch, collection
):
    monkeypatch.setattr(catalogue, "bank_for", lambda *a: pytest.fail("Noncausal propagation"))
    with pytest.raises(ValueError, match="noncausal or too old"):
        catalogue.prepare_catalogue(
            dict(elements={"1": dict(element_epoch_utc_ns=epoch, collected_utc_ns=collection)}),
            dict(cutoff_utc_ns=0, origin_utc_ns=0),
        )
