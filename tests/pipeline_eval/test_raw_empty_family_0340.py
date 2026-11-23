"""Keep the 0340 diagnostic warm-only and limit the raw invocation change to the guard."""

from pathlib import Path

import pytest

from raw_empty_family_0340 import FLAG, MEMBERS, PAGES, command, fully_resident


def test_warm_only_gate_requires_all_original_pages_and_members():
    resident = dict(cached_pages=PAGES, observed_file_pages=PAGES, members=MEMBERS, observed_members=MEMBERS, unavailable={})
    assert fully_resident(resident)
    assert not fully_resident(resident | {"cached_pages": PAGES-1})
    assert not fully_resident(resident | {"observed_members": MEMBERS-1})
    assert not fully_resident(resident | {"unavailable": {"input": "missing"}})


def test_command_keeps_the_recording_offer_archive_and_libraries(tmp_path):
    previous = ["python", "-IB", "/prior/short_cfo_raw.py", "--recording", "/raw", "--region", "/offer", "--archive", "/tle",
                "--output", "/prior/results", "--cfo-refinement-library", "/pinned/refine.so", "--prove-no-active-curvature"]
    argv = command(tmp_path, previous)
    assert Path(argv[2]).name == "short_cfo_raw.py"
    assert argv[3:10] == previous[3:10]
    assert argv[10] == str(tmp_path/"candidate")
    assert argv[11:] == previous[11:]+[FLAG]
    assert previous[10] == "/prior/results"
    with pytest.raises(ValueError, match="original refined raw command"):
        command(tmp_path, previous+[FLAG])
