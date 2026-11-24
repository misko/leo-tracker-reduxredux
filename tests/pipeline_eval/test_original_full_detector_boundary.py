import pytest

from reports.ALGO08.v3.original_full_detector_boundary import boundaries
from reports.ALGO08.v3.original_prefix_scaling import DetectionPublished, detection_hook


def test_same_prefix_hook_accepts_complete_authority_before_commit(tmp_path):
    native = {"source": {"raw_recording_authority_digest": "signed"}}
    live = {"source": {"authority_mode": "verified-once", "verified_source": {"windows": 4},
                       "finished_raw_authority": "signed"}}
    writes = []

    def commit(path, document):
        writes.append((path, document))

    for invalid in (
        detection_hook(tmp_path, live, 5, (), commit),
        detection_hook(tmp_path, live, 4, ("sys",), commit),
    ):
        with pytest.raises(ValueError, match="EOF"):
            invalid(native, None)
    with pytest.raises(ValueError, match="EOF"):
        detection_hook(tmp_path, live, 4, (), commit)({"source": {"raw_recording_authority_digest": "other"}}, None)
    assert writes == []
    with pytest.raises(DetectionPublished):
        detection_hook(tmp_path, live, 4, (), commit)(native, None)
    assert writes == [(tmp_path / "detections.json", native)]
    assert live["detector_published_unix_ns"] > 0


def test_boundaries_keep_both_file_and_return_clocks():
    clock = {"started_unix_ns": 1_000_000_000, "elapsed_s": 6.0}
    live = dict(acquire_started=1_500_000_000, acquire_ended=4_500_000_000,
                selector_started=4_600_000_000, selector_file_mtime=4_800_000_000,
                selector_ended=4_900_000_000, detector_published_unix_ns=5_200_000_000)
    timing = boundaries(clock, live, 5_100_000_000)
    assert timing["selector_file_s"] == pytest.approx(3.8)
    assert timing["selector_file_to_detection"] == pytest.approx(.3)
    assert timing["selector_return_to_detection"] == pytest.approx(.2)
    assert timing["detection_s"] == pytest.approx(4.2)
    assert timing["after_detector_s"] == pytest.approx(1.8)
    with pytest.raises(ValueError, match="unordered"):
        boundaries(clock, live, 4_500_000_000)
