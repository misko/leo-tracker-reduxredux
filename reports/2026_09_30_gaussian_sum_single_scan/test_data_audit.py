import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("data_audit", HERE / "generate_data_audit.py")
assert SPEC and SPEC.loader
audit_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_module)


def test_audit_accounts_for_every_frozen_unit_and_gate_status():
    audit = audit_module.build_audit()
    assert {name: row["units"] for name, row in audit["datasets"].items()} == {
        "DS9": 8, "DS10": 8, "DS11": 32,
    }
    assert audit["fit_accounting"] == {"smoke_ready_not_started": 1, "pending_not_started": 47}
    assert all(all(row["bindings"][key] for key in (
        "source_hash_verified", "inventory_binding_verified", "manifest_binding_verified"
    )) for row in audit["units"])


def test_runner_grouping_is_deterministic():
    first = audit_module.build_audit()
    second = audit_module.build_audit()
    left = [(row["unit_id"], row["runner_independent_tracks"]) for row in first["units"]]
    right = [(row["unit_id"], row["runner_independent_tracks"]) for row in second["units"]]
    assert left == right
