from gzip import compress
from hashlib import sha256

import numpy as np
import pytest

from reports.ALGO08.v3.owner_time_support import MAX_GAP, SAMPLE_RATE, design, read_features, support


@pytest.mark.parametrize("suffix", [".json", ".json.gz"])
def test_feature_identity_is_the_same_across_storage_encodings(tmp_path, suffix):
    body = b'{"features":[]}\n'
    path = tmp_path / ("sealed" + suffix)
    path.write_bytes(compress(body) if suffix.endswith(".gz") else body)
    assert read_features(path, sha256(body).hexdigest()) == body
    with pytest.raises(ValueError, match="sealed JSON"):
        read_features(path, "0"*64)


def test_quadratic_information_matches_independent_least_squares():
    seconds = np.array([0., .2, .8, 1.1, 2.4])
    counters = [321_345_678_999 + int(round(t*SAMPLE_RATE)) for t in seconds]
    regressors = np.column_stack((np.ones(len(seconds)), seconds))
    fitted = regressors @ np.linalg.lstsq(regressors, seconds**2, rcond=None)[0]
    expected = np.sum((seconds**2 - fitted)**2)
    assert design(counters) == pytest.approx((5, np.sum((seconds-seconds.mean())**2), expected))
    assert design(counters[::-1]) == pytest.approx(design(counters))


def test_retaining_the_middle_three_costs_more_time_support_than_spanning_the_ends():
    rows = [(i*SAMPLE_RATE, i in (1,2,3), i in (0,2,4)) for i in range(5)]
    result = support({"curve": rows})
    middle, spread = (result["loss"][key] for key in ("corroborated", "anchors"))
    assert middle["count"] == spread["count"] == pytest.approx(.4)
    assert middle["slope"] > spread["slope"]
    assert middle["quadratic"] > spread["quadratic"]


def test_fragmentation_uses_the_original_curve_before_filtering():
    rows = [(t*SAMPLE_RATE, t in (0,6,12), t == 6) for t in (0,3,6,9,12)]
    rows.append((12*SAMPLE_RATE + MAX_GAP + 1, True, True))
    report = support({"s1":rows, "s2":[(0, True, True)]})
    assert report["segments"] == 3
    assert report["totals"]["anchors"][2] == 0
    assert report["totals"]["corroborated"][2] == pytest.approx(design([i*SAMPLE_RATE for i in (0,6,12)])[2])
    assert report["totals"]["all"][0] == 7


def test_degenerate_design_is_unavailable():
    assert design([]) == (0,0,0)
    assert design([2,2,2]) == (3,0,0)
    assert support({"g":[(100, True, True)]})["loss"]["anchors"] == dict(count=0., slope=None, quadratic=None)
