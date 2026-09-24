import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
# The report path is intentionally explicit so this test also exercises the
# checked-in reproduction entry point.
SPEC = importlib.util.spec_from_file_location(
    "build_final_summary", HERE / "build_final_summary.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_final_summary_has_no_qualified_subkm_validation_claim() -> None:
    summary = MODULE.build()
    qualified = {
        "primary_ds1",
        "conditional_fixed_identity",
        "bounded_feasibility",
        "negative_transfer_control",
    }
    assert summary["reference_used_for_fit"] is False
    assert summary["held_used_for_fit"] is False
    assert not any(
        row["sub_km_validation"] for row in summary["rows"] if row["qualification"] in qualified
    )


def test_shared_time_improves_primary_ds1_medians() -> None:
    rows = {row["method_id"]: row for row in MODULE.build()["rows"]}
    baseline = rows["baseline"]
    shared = rows["shared_time"]
    assert shared["train_error_km"] < baseline["train_error_km"]
    assert shared["validation_error_km"] < baseline["validation_error_km"]
    assert shared["test_error_km"] < baseline["test_error_km"]
    assert shared["full_block_error_km"] < baseline["full_block_error_km"]
