from pathlib import Path

import pytest

from reports.ALGO08.v3 import legacy_block_all_0016 as trial, legacy_block_all_entry as entry


def test_selected_command_preserves_old_raw_scope_and_renderer(tmp_path):
    original = ["timeout", "--kill-after=2s", "75s", "python", "-IB", "/released/legacy_block_raw_entry.py",
                "--history-risk-route", "--cairo-residual-layout", "--portable-orbit-index", "index",
                "--recording", "original", "--region", "containing", "--archive", "causal", "--output", "old"]
    candidate = trial.projected_command(original, tmp_path / "indexed", tmp_path / "maps", "plan", "lib")
    assert candidate[:5] == original[:5]
    assert Path(candidate[5]).name == "legacy_block_all_entry.py"
    assert candidate[6:17] == original[6:17]
    assert candidate[17] == str(tmp_path / "indexed")
    assert candidate[18:] == ["--legacy-map-custody", str(tmp_path / "maps/custody.json"),
                             "--legacy-map-custody-sha256", "plan", "--legacy-map-library",
                             str(tmp_path / "maps/legacy-block.so"), "--legacy-map-library-sha256", "lib"]
    assert original[-1] == "old"
    with pytest.raises(ValueError, match="scientific experiment"):
        trial.projected_command([*original, "--visit-frame-custody"], tmp_path, tmp_path, "plan", "lib")


def test_map_kinds_bind_exact_external_pins_and_explicit_ordinary():
    literal = {"map_kind": "literal", "map_sha256": "literal-pin", "map": "literal-file"}
    exceptional = {"map_kind": "exception", "map_sha256": "exception-pin", "map": "exception-file"}
    ordinary = {"map_kind": "ordinary", "map_sha256": None, "map": None}
    assert entry.map_kinds({"members": [literal, exceptional, ordinary, ordinary]}) == {
        "literal-pin": "literal", "exception-pin": "exception"
    }
    for invalid in [dict(exceptional, map_sha256=literal["map_sha256"]), dict(exceptional, map=None),
                    dict(ordinary, map_kind="exception")]:
        with pytest.raises(ValueError, match="unambiguously"):
            entry.map_kinds({"members": [literal, invalid]})
