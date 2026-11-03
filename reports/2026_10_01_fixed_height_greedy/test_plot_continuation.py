import pytest
from plot_continuation import generate, validate_continuation


def _document():
    rows = []
    for dataset, count in (("DS9", 22), ("DS10", 21), ("DS11", 21)):
        for index in range(count):
            primary = {
                "unit_id": f"{dataset}-{index}", "dataset": dataset,
                "attempted": True, "sealed": True, "numerically_converged": True,
                "accepted": True,
                "error_m": 100.0, "east_km": 1.0, "north_km": 2.0,
            }
            rows.append({
                "unit_id": primary["unit_id"], "dataset": dataset, "primary": primary,
                "continuation_attempted": False, "effective_accepted": True,
                "effective_error_m": 100.0, "effective_east_km": 1.0,
                "effective_north_km": 2.0,
            })
    return {"schema": "fixed-height-t4-continuation-evaluation/v1",
            "planned_units": 64, "publication_ready": True, "rows": rows}


def test_complete_continuation_panel_accepts_retained_primary_successes() -> None:
    assert len(validate_continuation(_document())) == 64


def test_unresolved_primary_requires_attempt_and_sealed_success() -> None:
    document = _document()
    row = document["rows"][0]
    row["primary"].update(sealed=False, accepted=False, numerically_converged=False, error_m=None,
                          east_km=None, north_km=None)
    row.update(effective_accepted=False, effective_error_m=None,
               effective_east_km=None, effective_north_km=None)
    with pytest.raises(ValueError, match="continuation attempt"):
        validate_continuation(document)
    row["continuation_attempted"] = True
    assert len(validate_continuation(document)) == 64
    row.update(effective_accepted=True, effective_error_m=50.0,
               effective_east_km=1.0, effective_north_km=2.0,
               continuation={"sealed": False})
    with pytest.raises(ValueError, match="must be sealed"):
        validate_continuation(document)


def test_generation_uses_declared_dataset_order(tmp_path) -> None:
    paths = generate(_document(), tmp_path)
    assert {path.name for path in paths} == {
        "continuation-error-ecdf-all64.png",
        "continuation-per-scan-errors-status.png",
    }
