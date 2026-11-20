import pytest

from tools.pipeline_eval.qualification import complete_detector_roster as official
from tools.pipeline_eval.qualification import prefix_evidence_figures as study


def measurement(method, status="ok", binding="capture"):
    return dict(
        id="recording",
        method=method,
        paired_capture_sha256=binding,
        original_request_sha256="request",
        catalog_sha256="catalogue",
        tile={"id": "offer"},
        result=dict(
            status=status,
            reason=None if status == "ok" else "Measured service timed out",
            boundary="Measured fixed receiver",
            metrics={},
            arms={
                a: {"latlon": [38, -123] if status == "ok" else None} for a in ("c0", "fitted_c")
            },
        ),
    )


def test_retrospective_keeps_the_unreturned_chosen_branch_as_a_separate_row():
    records = [measurement(official.FOUR), measurement(official.FIVE, "timed_out")]
    chosen, stock, fifth = study.retabulate(records, {"recording": {"chosen": "fifth"}})
    assert len({r["method"] for r in (chosen, stock, fifth)}) == 3
    assert chosen["method"] == study.RETROSPECTIVE
    assert chosen["source_method"] == official.FIVE
    assert chosen["result"] == records[1]["result"] == fifth["result"]
    assert chosen["result"]["arms"]["c0"]["latlon"] is None
    assert stock["result"]["status"] == "ok"


def test_actual_chart_preserves_only_genuine_measured_mixed_rows_and_exact_controls():
    stock, fifth, fit = (measurement(m) for m in (official.FOUR, official.FIVE, study.ACTUAL))
    rows = study.actual_rows([stock, fifth, fit], ["recording"])
    assert {r["method"] for r in rows} == {study.STOCK, study.FIFTH, study.ACTUAL}
    assert rows[-1]["result"] == fit["result"]
    with pytest.raises(ValueError, match="different original measurements"):
        study.actual_rows([stock, fifth, dict(fit, paired_capture_sha256="other")], ["recording"])
    with pytest.raises(ValueError, match="Missing scheduled prediction row"):
        study.actual_rows([stock, fifth], ["recording"])
