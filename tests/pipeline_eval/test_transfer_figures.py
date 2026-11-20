import csv
import hashlib
import json
from collections import Counter, defaultdict

import pytest

from tools.pipeline_eval import __main__ as cli
from tools.pipeline_eval.corpus import references
from tools.pipeline_eval.qualification import transfer_figures as transfer
from tools.pipeline_eval.scoring import distance_km, distribution, thresholds


@pytest.fixture(scope="module")
def books(tmp_path_factory):
    out = tmp_path_factory.mktemp("transfer-figures")
    transfer.generate(out, ("fitted_c", "c0"))
    return out


def _errors(rows):
    return [float(row["error_km"]) for row in rows if row["error_km"]]


def test_fresh_subset_figures_keep_withheld_unmeasured_and_missing_offers_distinct(tmp_path):
    cases = [r for r in references("transfer124") if r["group"] == "StarLoc"]
    refs = [
        next(r for r in cases if r["condition"] == condition)
        for condition in ("present", "missing")
    ]
    measured = {refs[0]["id"]: dict(result=dict(status="ok", boundary="detector only", metrics={}))}
    rows = transfer._score_rows("new-receiver", "c0", refs, measured, source="predictions.jsonl")
    publications = {
        r["query_id"]: r["decision"] for r in rows if r["series"] == "candidate_published"
    }
    assert publications == {refs[0]["id"]: "stage_only", refs[1]["id"]: "missing"}
    result = cli.scored_files("transfer16", "new-receiver", refs, measured, tmp_path)
    assert result["statuses"] == {"ok": 1, "missing": 1}
    for arm in ("c0", "fitted_c"):
        assert (tmp_path / f"position-errors-{arm}.png").read_bytes().startswith(b"\x89PNG")


def test_unoffered_condition_in_custom_run_never_borrows_the_matching_query():
    case = next(r for r in references("transfer124") if r["group"] == "StarLoc")
    arm = dict(latlon=None, forced_latlon=None)
    record = dict(result=dict(status="withheld", arms=dict(c0=arm, fitted_c=arm)))
    rows = transfer._score_rows("custom", "c0", [case], {case["id"]: record}, source="predictions")
    fig = transfer._draw(rows, "custom", "c0", live=True)
    try:
        labels = {s.get_text() for ax in fig.axes for s in ax.texts}
        assert "No queries" in labels
        assert "0/1" in labels
    finally:
        transfer.plt.close(fig)


@pytest.mark.parametrize("arm", ["fitted_c", "c0"])
def test_transfer_figures_score_each_offer_pair_against_the_saved_reports(books, arm):
    report = transfer.ORIGINAL.parents[1]
    archived = json.loads((report / "results.json").read_text())
    summaries = archived["panels"]["transfer124"]
    shared = transfer.SOURCES["shared_doppler"]
    summaries["shared_doppler"] = json.loads(shared.with_name("transfer-summary.json").read_text())
    arc = transfer.SOURCES["arc_validation"]
    summaries["arc_validation"] = json.loads(arc.with_name("transfer-summary.json").read_text())
    arc_digest = hashlib.sha256(arc.read_bytes()).hexdigest()
    assert arc_digest == summaries["arc_validation"]["prediction_sha256"]
    for method, source in transfer.SOURCES.items():
        if source.is_relative_to(report):
            assert (
                hashlib.sha256(source.read_bytes()).hexdigest()
                == archived["prediction_sha256"][str(source.relative_to(report))]
            )
        assert (books / arm / f"{method}.png").read_bytes().startswith(b"\x89PNG")
    assert (books / arm / "modifications.pdf").read_bytes().startswith(b"%PDF")
    with (books / arm / "modifications.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    refs = {case["id"]: case for case in references("transfer124")}
    assert len(rows) == 124 * len(transfer.SOURCES) * 4
    assert {row["arm"] for row in rows} == {arm}
    for method, summary in summaries.items():
        method_rows = [row for row in rows if row["method"] == method]
        assert Counter(r["query_id"] for r in method_rows) == dict.fromkeys(refs, 4)
        assert Counter(r["acquisition_id"] for r in method_rows) == dict.fromkeys(
            {case["recording"] for case in refs.values()}, 8
        )
        samples = defaultdict(list)
        for row in method_rows:
            case = refs[row["query_id"]]
            assert row["dataset"] == case["group"]
            assert row["acquisition_id"] == case["recording"]
            assert row["correct_region_offered"] == str(case["condition"] == "present")
            samples[case["group"], case["condition"], row["series"]].append(row)
            if row["series"].startswith("grid_"):
                original = case["reference"][row["source_field"]]["shape"]
                assert _errors([row]) == (
                    pytest.approx([original["error_km"]], abs=1e-8)
                    if original["latlon"] is not None
                    else []
                )

        for group in (group for group in summary["groups"] if group["arm"] == arm):
            key = group["group"], group["condition"]
            published = samples[*key, "candidate_published"]
            guesses = samples[*key, "candidate_best_guess"]
            grid = samples[*key, "grid_published"]
            assert len(published) == len(guesses) == len(grid) == group["attempts"]
            assert Counter(r["decision"] for r in published) == group["decision_counts"]
            assert sum(r["false_publication"] == "True" for r in published) == (
                group["false_publications"] or 0
            )
            assert not any(r["false_publication"] == "True" for r in grid)
            assert thresholds(_errors(published)) == group["within_km"]
            assert distribution(_errors(published)) == group["error_km"]
            if method == "shared_doppler" and key[0] == "Altrincham":
                assert {r["source_field"] for r in guesses} == {""}
            if method == "projected_fit" and key == ("Synthetic", "present"):
                accepted = [
                    r for r in guesses if r["source_field"] == "latlon (accepted pooled point)"
                ]
                assert len(accepted) == 1
                assert _errors(accepted) == _errors(published)
                guesses = [r for r in guesses if r not in accepted]
            assert distribution(_errors(guesses)) == group["forced_error_km"]


def test_an_explicit_best_guess_is_distinct_from_false_publication():
    case = next(case for case in references("transfer124") if case["condition"] == "missing")
    point = case["truth"]
    guess = [0, 0]
    record = {
        "input_sha256": "fixture",
        "result": {"arms": {"c0": {"latlon": point, "forced_latlon": guess}}},
    }
    rows = transfer._score_rows("shared_doppler", "c0", [case], {case["id"]: record})
    outcomes = {r["series"]: (r["decision"], r["false_publication"], r["error_km"]) for r in rows}
    assert outcomes["candidate_published"] == ("published", True, 0)
    assert outcomes["candidate_best_guess"] == ("estimate", None, distance_km(point, guess))


def test_longitude_archive_rejects_a_mismatched_portable_input(monkeypatch):
    monkeypatch.setattr(transfer, "_selection", lambda panel: (["case"], {}))
    monkeypatch.setattr(
        transfer,
        "_read_frozen",
        lambda *_: b'{"id":"case","observation":"matched-track","catalog":"matched-orbit"}',
    )
    record = {"observation_sha256": "different-track", "catalog_sha256": "matched-orbit"}
    with pytest.raises(ValueError, match="portable inputs differ"):
        transfer._longitude_transfer({"case": record}, {"case": "archived-input-digest"})


def test_longitude_figure_rejects_predictions_changed_after_seal(tmp_path):
    source = tmp_path / "predictions.jsonl.gz"
    source.write_bytes(b"Changed prediction bytes")
    (tmp_path / "prediction-lock.json").write_text(
        json.dumps({"files": {source.name: hashlib.sha256(b"Original prediction").hexdigest()}})
    )
    with pytest.raises(ValueError, match="prediction seal"):
        transfer._longitude_evidence(source)


@pytest.mark.parametrize("arm", ("c0", "fitted_c"))
def test_longitude_figures_use_each_paired_comparison(books, arm):
    method = transfer.LONGITUDE_GATE
    source = transfer.SOURCES[method]
    statistics = json.loads(source.with_name("scores.json").read_bytes())["groups"]
    archives = (books / arm / "modifications.csv").read_text()
    historical = [row for row in csv.DictReader(archives.splitlines()) if row["method"] == method]
    refs = {r["id"]: r for r in references("transfer124")}
    assert Counter(r["query_id"] for r in historical) == dict.fromkeys(refs, 4)
    for row in historical:
        if row["series"].startswith("grid_"):
            expected = refs[row["query_id"]]["reference"][row["source_field"]]["shape"]["error_km"]
            errors = _errors([row])
            assert errors == ([] if expected is None else pytest.approx([expected], abs=1e-8))
    folder = books / arm
    assert (folder / "fresh80.png").read_bytes().startswith(b"\x89PNG")
    assert (folder / "fresh80.pdf").read_bytes().startswith(b"%PDF")
    with (folder / "fresh80.csv").open(newline="") as stream:
        fresh = list(csv.DictReader(stream))
    assert Counter(r["acquisition_id"] for r in fresh) == dict.fromkeys(
        {r["acquisition_id"] for r in fresh}, 8
    )
    assert len(fresh) == 80 * 4
    for group in statistics:
        if group["arm"] != arm or group["group"] != "all":
            continue
        if group["panel"] == "fresh80":
            rows = fresh
            series = "candidate_published" if group["method"] == method else "arc_published"
        elif group["method"] == method:
            rows = historical
            series = "candidate_published"
        else:
            continue
        offered = str(group["condition"] == "present")
        sampled = [
            r for r in rows if r["correct_region_offered"] == offered and r["series"] == series
        ]
        assert len(sampled) == group["attempts"]
        assert thresholds(_errors(sampled)) == group["within_km"]
        assert distribution(_errors(sampled)) == group["published_error_km"]
        assert Counter(r["decision"] for r in sampled)["published"] == group["publications"]
        if offered == "False":
            assert (
                sum(r["false_publication"] == "True" for r in sampled)
                == group["false_publications"]
            )
