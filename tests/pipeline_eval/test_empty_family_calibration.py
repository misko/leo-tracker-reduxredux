from types import SimpleNamespace

import numpy as np
import pytest

from reports.ALGO08.v3.empty_family_calibration import exclusion_witness, guarded_inference


def context(keep, families=(2, 8, 2)):
    keep = np.array(keep)
    base = SimpleNamespace(values=np.ones(6), rows=[{"candidate_index": f} for f in families],
                           slices=[slice(0, 2), slice(2, 4), slice(4, 6)])
    return {"base": base, "keep": keep}


def test_only_remaining_curved_family():
    d = context([True, False, False, False, True, True])
    before = d["keep"].copy()
    assert exclusion_witness(d) == dict(candidate_index=2, retained_rows=3, contributing_tracks=2,
                                        independent_rows=0)
    np.testing.assert_array_equal(before, d["keep"])
    d["keep"][2] = True
    assert exclusion_witness(d) is None


@pytest.mark.parametrize("keep", [[False]*6, [True]*5, [[True]*6], [1]*6])
def test_empty_or_invalid_design_goes_to_original(keep):
    assert exclusion_witness(context(keep)) is None


def test_uncovered_rows_do_not_trigger():
    d = context([True, False, False, False, False, True])
    d["base"].slices[-1] = slice(4, 5)
    assert exclusion_witness(d) is None


def test_only_certified_nominations_withheld(monkeypatch):
    from leo.analysis.localization_v3 import family_cavity

    def fail(d):
        raise ValueError("other nomination failure")

    monkeypatch.setattr(family_cavity, "nominate_families", fail)
    def infer(d):
        return family_cavity.nominate_families(d)

    outcome = guarded_inference(infer, context([True, False, False, False, True, True]))
    assert outcome["reason"] == "no_independent_family_calibration"
    assert all(r == {"latlon": None} for r in outcome["arms"].values())
    with pytest.raises(ValueError, match="other nomination failure"):
        guarded_inference(infer, context([True]*6))
    assert family_cavity.nominate_families is fail
