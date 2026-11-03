import pytest
from south_all_sky_audit import circular_coverage


def test_circular_coverage_unions_overlaps_and_handles_alias_boundary():
    assert circular_coverage([], 5., 100.) == 0.
    assert circular_coverage([0.], 5., 100.) == pytest.approx(.1)
    assert circular_coverage([0., 100.], 5., 100.) == pytest.approx(.1)
    assert circular_coverage([98., 2.], 5., 100.) == pytest.approx(.14)
    assert circular_coverage([0., 25., 50., 75.], 12.5, 100.) == pytest.approx(1.)
