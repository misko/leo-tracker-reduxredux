from copy import deepcopy
from pathlib import Path
import importlib.util
import sys


PATH = Path(__file__).with_name("calibrate_topology_reception.py")
SPEC = importlib.util.spec_from_file_location("topology_reception_calibration", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def rows():
    result = []
    for split, sid in (("cal", "c1"), ("cal", "c2"), ("holdout", "h")):
        for track, east in (("keep", -1.), ("remove", 1.)):
            for receiver in ("rx0", "rx1"):
                result.append({"session_id": sid, "split": split, "track_id": track,
                    "receiver_id": receiver, "channel": 1, "edge": "lower",
                    "sample_rate_hz": 2_500_000, "anchor_margin": 1.5,
                    "matched": (receiver == "rx0") == (east > 0),
                    "log_margin_ratio_rx1_rx0": east, "east": east, "up": .8})
    return result


def audit():
    sessions = []
    for split, ids in (("calibration", ("c1", "c2")),
                       ("confirmation", ("f1", "f2", "f3", "f4"))):
        for sid in ids:
            sessions.append({"session_id": sid, "split": split,
                             "removed_track_ids": ["remove"] if sid == "c1" else []})
    return {"sessions": sessions}


def test_excludes_all_rows_of_audited_tracks_and_accounts():
    retained, accounting = MODULE.topology_filtered_rows(rows(), audit(), {"c1", "c2"})
    assert not any(row["session_id"] == "c1" and row["track_id"] == "remove"
                   for row in retained)
    assert all(row["split"] == "cal" for row in retained)
    assert accounting["removed_calibration_tracks"] == 1
    assert accounting["removed_calibration_rows"] == 2


def test_holdout_perturbation_cannot_change_fit_or_scaling():
    original = rows()
    changed = deepcopy(original)
    for row in changed:
        if row["split"] == "holdout":
            row.update(east=999., anchor_margin=1e8,
                       matched=not row["matched"], log_margin_ratio_rx1_rx0=-999.)
    first = MODULE.fit_calibration(original, audit(), {"c1", "c2"})
    second = MODULE.fit_calibration(changed, audit(), {"c1", "c2"})
    assert first == second


def test_incomplete_or_wrong_audit_fails_closed():
    broken = audit()
    broken["sessions"].pop()
    try:
        MODULE.topology_filtered_rows(rows(), broken, {"c1", "c2"})
    except ValueError as error:
        assert "incomplete" in str(error)
    else:
        raise AssertionError("incomplete audit was accepted")
