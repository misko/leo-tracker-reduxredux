import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("panel_accounting", HERE / "generate_panel_accounting.py")
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_primary_panel_and_nonindependent_attempt_accounting():
    result = module.build_accounting()
    panel = result["planned_panel"]
    assert (panel["units"], panel["arms_per_unit"], panel["attempts"]) == (48, 3, 144)
    assert panel["attempted"] == 3
    assert panel["pending_not_started_gate"] == 141
    assert len(result["stress_attempts_outside_primary_panel"]) == 1
    assert len(result["superseded_v1_engineering_attempts"]) == 3


def test_all_native_seals_inputs_and_state_artifacts_verify():
    result = module.build_accounting()
    attempts = result["stress_attempts_outside_primary_panel"] + result["superseded_v1_engineering_attempts"]
    attempted_paths = {row["attempt_receipt"] for row in result["planned_panel"]["rows"] if row["attempt_receipt"]}
    attempts += [module.verify_attempt(Path(path), revision="v2") for path in attempted_paths]
    assert all(row["verification"][key] for row in attempts for key in ("seal", "inputs", "state"))
