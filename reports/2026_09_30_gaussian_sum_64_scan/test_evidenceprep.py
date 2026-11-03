import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("evidenceprep", HERE / "evidenceprep.py")
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_selection_counts_endpoints_and_unique_units():
    result = module.freeze_selection()
    assert result["counts"] == {"DS9": 22, "DS10": 21, "DS11": 21}
    units = [row["unit_id"] for rows in result["selected"].values() for row in rows]
    assert len(units) == len(set(units)) == 64
    assert result["selected"]["DS9"][0]["unit_id"] == "DS9-F001"
    assert result["selected"]["DS9"][-1]["unit_id"] == "DS9-F105"
    assert result["selected"]["DS10"][-1]["unit_id"] == "DS10-F187"
    assert result["selected"]["DS11"][-1]["unit_id"] == "DS11-F087"


def test_checked_in_selection_and_inventory_are_fully_bound():
    assert json.loads((HERE / "selection.json").read_text()) == module.freeze_selection()
    inventory = json.loads((HERE / "inventory.json").read_text())
    assert inventory["counts"] == {"ready": 64, "missing_selected_export": 0}
    assert all(row["accepted_exports"] for row in inventory["rows"])
    assert all(item["status"] == "complete" for item in inventory["observation_exports"])


def test_all_orbit_banks_are_causal_hash_bound_and_complete():
    selection = json.loads((HERE / "selection.json").read_text())
    rows = [row for group in selection["selected"].values() for row in group]
    assert len(rows) == 64
    for row in rows:
        evidence = json.loads((HERE / "evidence" / f"{row['unit_id']}.json").read_text())
        metadata = json.loads((HERE / "evidence" / f"{row['unit_id']}-orbits.json").read_text())
        state = HERE / "evidence" / f"{row['unit_id']}-orbits.npz"
        assert state.is_file()
        assert metadata["session_id"] == evidence["session_id"] == row["session_id"]
        assert metadata["observation_sha256"] == evidence["source"]["sha256"]
        assert metadata["tle"]["causal"] is True
        assert metadata["state_sha256"] == module.digest(state)
        assert metadata["propagated_count"] + metadata["propagation_rejected_count"] == metadata["catalogue_count"]
