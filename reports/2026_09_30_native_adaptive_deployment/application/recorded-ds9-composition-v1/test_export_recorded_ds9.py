#!/usr/bin/env python3
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("export_recorded_ds9", HERE / "export_recorded_ds9.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_selection_contract() -> None:
    assert MODULE.selected_visits("visit301", Path("missing")) == [301]
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "selection.json"
        visits = [
            {"visit": value, "persisted_outcome": "must-not-enter-plan"}
            for value in reversed(range(32))
        ]
        path.write_text(json.dumps({
            "schema": "org.leo.ds9-corrected-wrapper-slice-selection/v1",
            "visits": visits,
        }))
        assert MODULE.selected_visits("panel32", path) == list(range(32))
        visits[-1]["visit"] = visits[0]["visit"]
        path.write_text(json.dumps({
            "schema": "org.leo.ds9-corrected-wrapper-slice-selection/v1",
            "visits": visits,
        }))
        try:
            MODULE.selected_visits("panel32", path)
            raise AssertionError("duplicate selection accepted")
        except ValueError:
            pass


def test_output_guards_before_store_access() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        existing = Path(temporary) / "existing"
        existing.mkdir()
        sentinel = existing / "sentinel"
        sentinel.write_text("keep")
        try:
            MODULE.export("visit301", existing, "/unreachable", Path("unused"))
            raise AssertionError("existing output accepted")
        except FileExistsError:
            pass
        assert sentinel.read_text() == "keep"
    try:
        MODULE.export("visit301", Path("/mnt/qnap01/forbidden"), "/unreachable", Path("unused"))
        raise AssertionError("QNAP output accepted")
    except ValueError:
        pass


def check_frozen_export(path: Path, expected_visits: int) -> None:
    bundle = json.loads((path / "bundle.json").read_text())
    assert bundle["schema"] == "org.leo.scanner-recorded-plan/v1"
    assert bundle["persisted_candidate_values_used_in_plan"] is False
    assert bundle["adaptive_policy_replayed"] is False
    assert len(bundle["visits"]) == expected_visits
    assert bundle["plan_digest"] == MODULE.canonical_sha256({
        key: bundle[key] for key in ("schema", "session", "calibration", "visits")
    })
    assert bundle["session"]["timing"]["qualified"] is True
    assert bundle["session"]["generation"] == 12478478914259975484
    native_lines = (path / "native.tsv").read_text().splitlines()
    assert native_lines[0] == "FORMAT\tleo-recorded-ds9/v1"
    assert sum(line.startswith("SESSION\t") for line in native_lines) == 1
    assert sum(line.startswith("TIMING\t") for line in native_lines) == 1
    assert sum(line.startswith("VISIT\t") for line in native_lines) == expected_visits
    for target in bundle["calibration"]["targets"]:
        assert target["profile_crc32"] == 0
    last_visit = -1
    last_end = -1
    for row in bundle["visits"]:
        assert row["visit"] > last_visit and row["valid_start"] >= last_end
        assert row["dwell_ms"] == 120 and row["expected_profile_crc32"] == 0
        assert row["expected_transition_flags"] == MODULE.RECORDED_TRANSITION_FLAGS
        assert "candidate" not in row and "persisted_outcome" not in row
        raw = path / row["raw_path"]
        assert raw.stat().st_size == row["raw_bytes"] == 7_200_000
        assert MODULE.file_sha256(raw) == row["raw_sha256"]
        last_visit, last_end = row["visit"], row["valid_end"]
    sums = json.loads((path / "SHA256SUMS.json").read_text())
    for relative, expected in sums.items():
        assert MODULE.file_sha256(path / relative) == expected


if __name__ == "__main__":
    test_selection_contract()
    test_output_guards_before_store_access()
    parser_output = Path("/var/tmp/leo-recorded-ds9-v2")
    check_frozen_export(parser_output / "visit301", 1)
    check_frozen_export(parser_output / "panel32", 32)
    print("recorded DS9 exporter tests: pass")
