import pytest
from plot_primary import failure_aware_ecdf, validate_complete


def _panel_rows():
    rows = []
    for dataset, count in (("DS9", 22), ("DS10", 21), ("DS11", 21)):
        rows.extend({
            "unit_id": f"{dataset}-{index}",
            "dataset": dataset,
            "attempted": True,
            "sealed": True,
            "accepted": True,
            "numerically_converged": True,
            "error_m": 100.0,
            "east_km": 1.0,
            "north_km": 2.0,
        } for index in range(count))
    return rows


def test_failure_aware_ecdf_keeps_failures_in_denominator() -> None:
    rows = [{"error_m": 100.0}, {"error_m": None}, {"error_m": 10.0}, {"error_m": None}]
    x, y = failure_aware_ecdf(rows, "error_m")
    assert x.tolist() == [10.0, 100.0]
    assert y.tolist() == [0.25, 0.5]


def test_publication_plot_rejects_incomplete_panel() -> None:
    with pytest.raises(ValueError, match="publication-ready"):
        validate_complete({
            "schema": "fixed-height-t4-primary-evaluation/v1",
            "planned_units": 64,
            "publication_ready": False,
            "rows": [],
        })


def test_launch_only_timeout_remains_in_publication_denominator() -> None:
    rows = _panel_rows()
    rows[0].update(
        sealed=False,
        accepted=False,
        numerically_converged=False,
        error_m=None,
        east_km=None,
        north_km=None,
        status="timeout",
    )
    document = {
        "schema": "fixed-height-t4-primary-evaluation/v1",
        "planned_units": 64,
        "publication_ready": True,
        "rows": rows,
    }
    assert len(validate_complete(document)) == 64
    rows[0]["attempted"] = False
    with pytest.raises(ValueError, match="attempt record"):
        validate_complete(document)
