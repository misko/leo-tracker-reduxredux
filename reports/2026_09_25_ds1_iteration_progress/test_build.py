import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("ds1_progress", HERE / "build.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_all_iterations_are_enumerated_once():
    rows = MODULE.build_rows()
    assert [row["iteration"] for row in rows] == list(range(1, 28))
    assert all(len(row["source"]["sha256"]) == 64 for row in rows)


def test_geography_and_model_only_results_are_separate():
    rows = MODULE.build_rows()
    assert all(row["postseal_geographic_error_km"] is None for row in rows[21:26])
    assert rows[18]["current_disposition"] == "audit"
    assert rows[19]["current_disposition"] == "diagnostic"
    assert rows[25]["current_disposition"] == "numerical_no_go"
    assert rows[26]["current_disposition"] == "search_open"
    assert rows[26]["postseal_geographic_error_km"] == 1.112841731176525


def test_generated_summary_does_not_claim_current_sub_km_qualification():
    MODULE.main()
    payload = json.loads((HERE / "progress.json").read_text())
    assert payload["interpretation"]["qualified_sub_km_current"] is False
    assert (
        "No current qualified sub-km" in payload["interpretation"]["current_geographic_conclusion"]
    )
