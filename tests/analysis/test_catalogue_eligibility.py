from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
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
