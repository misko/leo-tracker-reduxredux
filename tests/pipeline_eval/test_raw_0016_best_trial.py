"""Component checks for the one-recording comparison's input and output boundaries."""

from pathlib import Path

import pytest

from raw_0016_best_trial import CASE, FLAGS, PROJECTION, check_extent, command, seal


def test_frozen_raw_mode_and_named_reference_share_all_causal_inputs(tmp_path):
    recording = Path("/recording")
    named = Path("/named/run")
    libraries = {key: Path("/lib")/key for key in ("short", "geographic", "regional", "block")} | {
        "projection": PROJECTION}
    candidate = command("candidate", tmp_path, recording, libraries, named)
    stock = command("stock", tmp_path, recording, libraries, named)
    for flag in ("--recording", "--region", "--archive"):
        assert candidate[candidate.index(flag)+1] == stock[stock.index(flag)+1]
    assert stock[0] == named
    assert candidate[-len(FLAGS):] == list(FLAGS)
    assert candidate[candidate.index("--grid-feature-projection-library")+1] == PROJECTION
    with pytest.raises(ValueError, match="one current candidate"):
        command("second-candidate", tmp_path, recording, libraries, named)


@pytest.mark.parametrize("extent, overrides", [
    (CASE.compressed_bytes-1, {}), (CASE.raw_limit+1, {}), (CASE.compressed_bytes, {"members": 14}),
    (CASE.compressed_bytes, {"observed_members": 12}), (CASE.compressed_bytes, {"unavailable": 1}),
])
def test_one_conditioning_extent_rejects_unbound_or_unreadable_members(extent, overrides):
    cache = dict(members=13, observed_members=13, unavailable=0, observed_file_pages=242_128)
    check_extent(cache, CASE.compressed_bytes)
    with pytest.raises(ValueError, match="conditioning extent"):
        check_extent(cache | overrides, extent)


def test_prediction_seal_covers_both_process_logs_and_actual_image_bytes(tmp_path):
    for file in ("admission.json", "offer.json", "conditioning-before.json", "conditioning.json"):
        (tmp_path/file).write_bytes(b"{}")
    for mode in CASE.order:
        (tmp_path/mode).mkdir()
        for suffix in ("-clock.json", ".stdout", ".stderr"):
            (tmp_path/f"{mode}{suffix}").write_bytes(b"{}")
        (tmp_path/mode/"position.png").write_bytes(b"png")
    initial = seal(tmp_path)
    (tmp_path/"candidate"/"position.png").write_bytes(b"changed png")
    changed = seal(tmp_path)
    assert set(initial) == set(changed)
    assert len(initial) == 12
    assert [key for key in initial if initial[key] != changed[key]] == ["candidate/position.png"]
