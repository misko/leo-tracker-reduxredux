import json
from copy import deepcopy

import pytest

from tools.pipeline_eval import corpus, coverage
from tools.pipeline_eval.__main__ import main, read_predictions
from tools.pipeline_eval.qualification.full_receiver_comparison import seal


def test_empirical_percentile_inverts_all_offer_curve_and_keeps_abstentions():
    assert coverage.at_coverage([0.0, 1, 1, None]) == {
        "offered": 4,
        "published": 3,
        "km_at_percent": {"50": 1, "75": 1, "90": None, "95": None},
    }
    assert coverage.at_coverage([0.0] * 19 + [None])["km_at_percent"]["95"] == 0
    assert set(coverage.at_coverage([])["km_at_percent"].values()) == {None}


def test_paired_margin_and_distributional_shortfall_answer_different_questions():
    result = coverage.comparison([(3, 1), (1, 3), (None, 1), (10, None)])
    assert (result["shared_fixes"], result["gained_fixes"], result["lost_fixes"]) == (2, 1, 1)
    assert result["relative_error_margin_percent"]["10"] == {
        "shared_within_margin": 1,
        "largest_cdf_shortfall_recordings": 1,
    }


def test_missing_region_counts_false_publications_in_both_arms_even_without_distance():
    ref = deepcopy(next(r for r in corpus.references("transfer124") if r["condition"] == "missing"))
    ref["truth"] = None
    ref["reference"] = {"baseline": {"c0": {"latlon": [0, 0]}, "fitted_c": {"latlon": None}}}
    arms = dict(c0={"latlon": None, "forced_latlon": [0, 0]}, fitted_c={"latlon": [1, 2]})
    result = dict(status="ok", boundary="native", metrics={}, arms=arms)
    rows = coverage.evaluate([ref], {ref["id"]: dict(result=result)})
    assert [(r["false_publications"], r["v5_false_publications"]) for r in rows] == [(0, 1), (1, 0)]
    assert all("matched" not in r for r in rows)


def test_normal_cli_seals_denominator_to_panel_even_for_an_empty_prediction_file(tmp_path, capsys):
    predictions, report = tmp_path / "predictions.jsonl", tmp_path / "out.json"
    predictions.touch()
    assert (
        main(
            [
                "coverage",
                "--panel",
                "ds26-all159",
                "--predictions",
                str(predictions),
                "--out",
                str(report),
            ]
        )
        == 0
    )
    rows = json.loads(report.read_bytes())
    assert rows == json.loads(capsys.readouterr().out)
    for row in rows:
        assert row["statuses"] == {"missing": 159}
        assert row["matched"]["original"]["published"] == 143
        assert row["matched"]["candidate"]["offered"] == 159
        assert set(row["candidate"]["km_at_percent"].values()) == {None}
    with pytest.raises(ValueError, match="outside"):
        coverage.evaluate([], {"foreign": {"result": {}}})


def test_full_roof_report_matches_the_sealed_stock_first_predictions():
    screen = corpus.REPO / "reports/2026_11_19_receiver_screening"
    study = screen / "integration/failed-only"
    archive = "all159-replay.jsonl.gz"
    receipt = seal(study, "all159-figure-lock.json", (archive,))
    forecasts = read_predictions(study / archive)
    assert set(forecasts) == set(receipt["cases"])
    rows = coverage.evaluate(corpus.references("ds26-all159"), forecasts)
    assert rows == json.loads((screen / "streamlined/coverage-159.json").read_bytes())
    assert all(r["matched"]["original"]["km_at_percent"]["90"] is None for r in rows)
    assert all(r["matched"]["candidate"]["km_at_percent"]["95"] < 7 for r in rows)
