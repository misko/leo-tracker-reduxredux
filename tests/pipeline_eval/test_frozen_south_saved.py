import json
import os
from pathlib import Path

import pytest

from reports.ALGO08.v3.frozen_south_saved import FREEZE_SHA, PINS, deny_original, digest


def test_signed_offer_pair_and_order():
    freeze = PINS / "frozen-build-geography.json"
    assert digest(freeze) == FREEZE_SHA
    pair = json.loads(freeze.read_bytes())["proposed_saved_pair"]
    offers = {}
    for name, item in pair["offers"].items():
        path = PINS / item["path"]
        assert digest(path) == item["sha256"]
        offers[name] = json.loads(path.read_bytes())
    containing, omitted = offers["containing"], offers["omitted"]
    assert containing["screen_center"] == omitted["screen_center"]
    assert containing["width_km"] == omitted["width_km"] == 25
    assert containing["center"][1] == omitted["center"][1]
    assert (containing["center"][0] - omitted["center"][0]) * 111 == pytest.approx(2)
    assert pair["planned_order"] == ["containing:installed", "containing:integrated", "omitted:integrated", "omitted:installed"]


def test_original_denial_and_unchanged_causal_archive(tmp_path):
    original, archive = tmp_path / "original", tmp_path / "archive"
    guard = deny_original(original, archive)
    guard("open", (str(archive / "tle.txt"), "r", os.O_RDONLY))
    guard("open", (str(tmp_path / "detections.json"), "r", os.O_RDONLY))
    guard("open", (1, "w", os.O_WRONLY))
    for path in (original, original / "manifest.json", tmp_path / "raw.ci16.zst",
                 Path("/srv/bulk/tle.txt"), Path("/mnt/qnap01/detections.json")):
        with pytest.raises(ValueError, match="cannot read an original source"):
            guard("open", (str(path), "r", os.O_RDONLY))
    with pytest.raises(ValueError, match="cannot change its causal archive"):
        guard("open", (str(archive / "tle.txt"), "r+", os.O_RDWR))
