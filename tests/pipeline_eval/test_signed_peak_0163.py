import gzip
from hashlib import sha256
import json

import pytest

from reports.ALGO08.v3 import signed_peak_0163 as p


HYPOTHESIS = dict(integer_epoch_sample=989, fractional_epoch_offset_samples=.6917107225133472,
                  fractional_tracking_cfo_hz=-49_126.353183411054)


def test_frozen_grid_preserves_sealed_center_and_symmetric_budget():
    points = list(p.grid(HYPOTHESIS))
    assert len(points) == 33*17
    assert points[len(points)//2] == (0, 0, 989, HYPOTHESIS["fractional_epoch_offset_samples"],
                                      HYPOTHESIS["fractional_tracking_cfo_hz"])
    for time, frequency, epoch, offset, hz in points:
        assert epoch + offset == pytest.approx(989 + HYPOTHESIS["fractional_epoch_offset_samples"] + time/4)
        assert hz == pytest.approx(HYPOTHESIS["fractional_tracking_cfo_hz"] + frequency*250)
        assert p.support_frames(epoch, offset) == 15


def test_out_of_neighborhood_residual_does_not_replace_a_local_peak():
    grid = p.surface(lambda *_: (.1, .02, 0., 2), HYPOTHESIS, 0.)
    assert grid["inside_count"] == len(grid["cells"]) == 561
    assert grid["best_margin"]["margin"] == pytest.approx(.08)
    aliased = p.surface(lambda *_: (.8, .02, p.ALIAS_HZ/2, 2), HYPOTHESIS, 0.)
    assert aliased["inside_count"] == 0 and aliased["best_exact"] is None
    assert aliased["unrestricted_best_exact"]["exact"] == .8


def test_waveform_access_is_limited_to_exact_enrolled_member():
    p.allow_local_waveform("open", (str(p.STAGE / "iq-000000.ci16.zst"),))
    for path in ("/srv/bulk/recording/manifest.json", "/tmp/other/iq-000000.ci16.zst", "/mnt/qnap01/wave"):
        with pytest.raises(PermissionError, match="enrolled resident original"):
            p.allow_local_waveform("open", (path,))


def test_sealed_physical_grid_preserves_all_cells_and_same_complete_support():
    from reports.ALGO08.v3.plot_signed_peak_0163 import PIN

    raw = (p.HERE / "measurements/0163-signed-peak-neighbourhood.json.gz").read_bytes()
    assert sha256(raw).hexdigest() == PIN
    runs = json.loads(gzip.decompress(raw))["results"]
    for run in runs.values():
        assert len(run["fixed_verifier_checks"]) == len(run["native_full"]) == 2
        for comparison in run["neighborhoods"].values():
            assert len(comparison["cells"]) == 561
            assert {c["frames"] for c in comparison["cells"]} == {15}
            assert sum(c["inside"] for c in comparison["cells"]) == comparison["inside_count"]
    peak = runs["61"]["neighborhoods"]
    assert peak["named"]["best_margin"]["margin"] > p.MARGIN_GATE
    assert all(not c["flags"] & 2 for c in peak["integrated"]["cells"])
