from types import SimpleNamespace

import numpy as np

import leo.analysis.catalogue_eligibility as eligibility
from leo.analysis.catalogue_eligibility import (
    exclude_labelled_starlink_debris,
    exclude_starlink_sgp4_failures,
)
from leo.sky.propagation import parse_element_sets
from tests.application.test_persistent_hop_tracking import _snapshot_payload


def test_only_explicit_debris_is_excluded_and_original_is_preserved():
    original = _snapshot_payload().replace("STARLINK-44714\n", "STARLINK-34343 DEB\n")
    eligible, exclusions = exclude_labelled_starlink_debris(original)
    assert len(parse_element_sets(original)) == 12
    assert len(parse_element_sets(eligible)) == 11
    assert len(exclusions) == 1 and exclusions[0].name == "STARLINK-34343 DEB"
    assert exclude_labelled_starlink_debris(original) == (eligible, exclusions)
    assert exclude_labelled_starlink_debris(_snapshot_payload())[1] == ()


def test_sgp4_failure_is_excluded_with_response_blind_receipt(monkeypatch):
    payload = _snapshot_payload()

    def propagate(_catalogue, grid, *, indices):
        errors = np.zeros((len(indices), len(grid.utc_ns)), dtype=np.int32)
        errors[1, :] = 6
        return SimpleNamespace(error_code=errors, usable=(errors == 0).all(axis=1))

    monkeypatch.setattr(eligibility, "propagate_grid", propagate)
    filtered, exclusions = exclude_starlink_sgp4_failures(
        payload, screened_utc_ns=(100, 200, 300, 400)
    )
    assert len(parse_element_sets(filtered)) == len(parse_element_sets(payload)) - 1
    assert len(exclusions) == 1
    assert exclusions[0].catalog_number == 44715
    assert exclusions[0].error_codes == (6,)
    assert exclusions[0].screened_utc_ns == (100, 200, 300, 400)
    assert exclusions[0].reason == "sgp4-propagation-error"
