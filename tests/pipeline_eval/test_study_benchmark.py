from types import SimpleNamespace

import pytest

from tools.pipeline_eval import __main__ as cli
from tools.pipeline_eval.position_figure import Mark
from tools.pipeline_eval.qualification import study_benchmark


def test_generic_roof_counts_each_matched_recording_and_keeps_withholdings():
    study = SimpleNamespace(id="r", scope="roof", labels={"one": "Single"}, predictions={"one": {}})
    page = SimpleNamespace(
        rows=[
            Mark("DS26", "a", "baseline", "published", 1.0),
            Mark("DS26", "a", "one", "published", 1.06),
            Mark("DS29", "b", "baseline", "published", 0.7),
            Mark("DS29", "b", "one", "withheld", None),
            Mark("DS29", "b", "one_forced", "diagnostic", 0.1),
        ]
    )
    rows = study_benchmark.summarize(study, page, "c0")
    row = next(r for r in rows if r["cohort"] == "all" and r["series"] == "one")
    assert (row["scheduled"], row["published"], row["withheld"], row["median_km"]) == (
        2,
        1,
        1,
        1.06,
    )
    assert (row["within_5pct"], row["within_10pct"]) == (0, 1)
    assert not any(r["series"] == "one_forced" for r in rows)


def test_generic_transfer_keeps_offers_distinct_and_fitted_unavailable():
    study = SimpleNamespace(id="r", scope="transfer", labels={}, predictions={"candidate": {}})
    page = SimpleNamespace(
        rows=[
            Mark("containing", "day1", "candidate", "published", 2.0),
            Mark("omitted", "day1", "candidate", "unavailable", None),
            Mark("omitted", "day1", "diagnostic", "diagnostic", 3.0),
        ]
    )
    rows = study_benchmark.summarize(study, page, "fitted_c")
    assert [r["cohort"] for r in rows] == ["containing", "omitted"]
    assert rows[1]["unavailable"] == 1 and rows[1]["median_km"] is None
    assert not any(r["within_10pct"] is not None for r in rows)


def test_study_and_receiver_selectors_are_mutually_exclusive(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(study_benchmark, "run", lambda *a: calls.append(a))
    monkeypatch.setattr(cli, "DEFAULT_OUT", tmp_path)
    assert cli.main(["benchmark", "--study", str(tmp_path / "trial")]) == 0
    assert calls == [(tmp_path / "trial", tmp_path / "trial-benchmark")]
    with pytest.raises(SystemExit):
        cli.main(["benchmark", "--study", str(tmp_path), "--receiver", "one-lane"])
