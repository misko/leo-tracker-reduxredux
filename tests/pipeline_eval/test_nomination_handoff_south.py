from pathlib import Path

import pytest

from reports.ALGO08.v3.nomination_handoff_south import single_segment_manifest, staged
from reports.ALGO08.v3.nomination_handoff_south_score import decision


def test_ram_path_admission_accepts_both_mounts_without_enabling_backing_paths():
    for root in (Path("/tmp"), Path("/dev/shm")):
        assert staged(root) == root
    with pytest.raises(ValueError, match="tmpfs"):
        staged(Path("/var/tmp"))


def test_mirror_does_not_call_a_complete_omission_a_fix():
    assert decision("complete", False) == "false_fix"
    assert decision("withheld", False) == "withheld"
    assert decision("complete", True) == "fix"
    assert decision("withheld", True) == "false_withhold"
    with pytest.raises(ValueError):
        decision("failed", False)


def test_already_canonical_root_manifest_keeps_the_original_signed_path():
    canonical = dict(recording="/tmp/recording", manifests=[["/tmp/recording/manifest.json", "signed"]])
    legacy = dict(canonical, manifests=[["/tmp/recording/segment", "signed"]])
    assert single_segment_manifest(lambda _: None, canonical) is canonical
    assert single_segment_manifest(lambda req: req["manifests"], legacy) == legacy["manifests"]
    multiple = dict(canonical, manifests=canonical["manifests"] + legacy["manifests"])
    assert single_segment_manifest(lambda req: req["manifests"], multiple) == multiple["manifests"]
