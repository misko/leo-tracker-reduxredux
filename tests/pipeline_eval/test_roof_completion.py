import gzip
from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification import roof_completion as study
from tools.pipeline_eval.qualification import screening_figures as figures
from tools.pipeline_eval.scoring import ARMS, ROLES


def sample(ident, *, attempted=False, status="missing", source="not_launched"):
    return dict(
        id=ident,
        method=study.COMPACT,
        mode="matched-tile",
        input_sha256="a" * 64,
        native_sha256="b" * 64,
        catalog_sha256="c" * 64,
        frozen_request_sha256="d" * 64,
        tile=dict(id="original", center=[37.0, -122.0]),
        attempted=attempted,
        source=source,
        deadline_s=195,
        result=dict(
            status=status,
            arms={arm: dict(latlon=None) for arm in ARMS},
        ),
    )


def test_add_only_keeps_actual_budget_failure_and_rejects_input_changes():
    first = {
        "A": sample("A"),
        "B": sample("B", attempted=True, status="failed", source="fresh"),
    }
    supplemental = {"A": sample("A", attempted=True, status="timed_out", source="supplement")}
    original = deepcopy(first)
    joined = study.add_only(first, supplemental)
    assert joined["A"]["result"]["status"] == "timed_out"
    assert joined["A"]["supplemental_attempt"]
    assert joined["B"] == original["B"]
    assert first == original
    with pytest.raises(ValueError, match="add-only"):
        study.add_only(first, supplemental | {"B": sample("B", attempted=True, status="ok")})
    with pytest.raises(ValueError, match="different catalog_sha256"):
        study.add_only(first, {"A": dict(supplemental["A"], catalog_sha256="e" * 64)})


def test_return_counts_distinguish_tolerance_and_improvement():
    result = study.paired([0, 2, 2, 3, None, None], [0, 2.2, 4, None, 1, None])
    assert result["both_fix"] == 3
    assert result["candidate_within_10pct"] == 3
    assert result["control_within_10pct"] == 2
    assert result["candidate_at_least_10pct_better"] == 1
    assert result["candidate_rescue"] == result["candidate_loss"] == result["neither_fix"] == 1
    assert study.outcome("missing", False, None) == "unattempted"
    assert study.outcome("missing", None, None) == "missing"


def test_sealed_original_budget_scoring_and_standard_figure_rosters(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_EVAL_BULK_ROOT", str(tmp_path / "unmounted"))
    result = study.publish(study.SCREEN, tmp_path, initial_only=True)
    folder = tmp_path / "budget"
    specs = study.read(folder / "figures.json")["charts"]
    assert [spec["id"] for spec in specs] == [
        "ds26_roof_completion-budget-all159",
        "ds26_roof_completion-budget-excluded32",
    ]
    for spec, n in zip(specs, (159, 32), strict=True):
        chart = figures._chart(folder, spec)
        assert len(chart.cases) == n
        for arm in ARMS:
            rows = chart.page(arm).rows
            assert {m.series for m in rows} == {*ROLES, "one", "stock"}
            for series in (*ROLES, "one", "stock"):
                assert len([m for m in rows if m.series == series]) == n
            unavailable = [m for m in rows if m.recording == "DS26-0172"]
            assert len(unavailable) == 6 and all(m.error_km is None for m in unavailable)
    for arm in ARMS:
        excluded = result["excluded32"]["position"][arm]
        assert excluded[study.COMPACT]["outcomes"] == dict(
            published=16,
            withheld=0,
            failed=6,
            timed_out=1,
            unavailable=1,
            unattempted=8,
            missing=0,
        )
        assert excluded[study.NATIVE]["outcomes"]["published"] == 23
        assert excluded["paired"][f"{study.NATIVE}_vs_{study.COMPACT}"]["both_fix"] == 14


def test_full_release_reproduces_sealed_add_only_and_calibration_pairs(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_EVAL_BULK_ROOT", str(tmp_path / "unmounted"))
    monkeypatch.setattr(study.corpus, "REPO", tmp_path / "clean")
    combined = study.publish(study.SCREEN, tmp_path)
    section = combined["excluded32"]
    compact = section["position"]["fitted_c"][study.COMPACT]
    assert compact["outcomes"] == dict(
        published=22,
        withheld=0,
        failed=8,
        timed_out=1,
        unavailable=1,
        unattempted=0,
        missing=0,
    )
    assert section["compact_execution_scope"]["initial_budget_unattempted"] == 8
    assert section["compact_execution_scope"]["supplemental_attempts"] == 8
    pair = section["position"]["fitted_c"]["paired"][f"{study.NATIVE}_vs_{study.COMPACT}"]
    assert (pair["both_fix"], pair["candidate_rescue"], pair["candidate_loss"]) == (17, 6, 5)
    assert pair["rescue_control_outcomes"] == dict(failed=5, timed_out=1)
    for result, field, n in (
        (study.COMPACT, "rf_rms_hz", 22),
        (study.NATIVE, "held_rf_rms_hz", 31),
    ):
        values = section["frequency_calibration"][result][f"fitted_minus_zero_{field}"]
        assert values["n"] == n and values["min"] < values["max"]
    assert combined["all159"]["scheduled"] == 159


def test_packed_original_scores_must_match_frozen_source(tmp_path):
    path = tmp_path / study.ORIGINAL_EXPORT
    path.parent.mkdir(parents=True)
    path.write_bytes(gzip.compress(b"altered archive"))
    with pytest.raises(ValueError, match="frozen source provenance"):
        study.original_scores(tmp_path)
