import csv
import json
import re
from collections import Counter

import pytest

from tools.pipeline_eval.qualification import cold_transfer_figures as charts


def test_transfer_evidence_keeps_matched_pairs_and_untargeted_shuffle_separate():
    rows, sources = charts.evidence_rows()
    assert len(rows) == 66
    assert "reports/2026_11_19_glrt_cold_start/scenes/predictions.jsonl.gz" in sources
    assert all("pre-correction" not in path and "setup-retry" not in path for path in sources)
    for method in charts.TITLES:
        for arm in charts.ARMS:
            sample = [r for r in rows if r["method"] == method and r["arm"] == arm]
            correct = {r["id"] for r in sample if r["cohort"] == "correct"}
            omitted = {r["id"] for r in sample if r["cohort"] == "omitted"}
            assert correct == omitted == set(charts.cold_missing.CASES)
            assert Counter(r["cohort"] for r in sample) == {
                "correct": 3,
                "omitted": 3,
                "synthetic": 4,
                "shuffle": 1,
            }
            (shuffle,) = [r for r in sample if r["cohort"] == "shuffle"]
            assert shuffle["status"] == "withheld"
            assert shuffle["error_km"] is shuffle["forced_error_km"] is None
            assert not any(r["false_publication"] for r in sample)
    (closest,) = [
        r
        for r in rows
        if r["method"] == "point_votes" and r["label"] == "Southern Africa" and r["arm"] == "c0"
    ]
    assert closest["status"] == "withheld"
    assert closest["forced_error_km"] == pytest.approx(2.629, abs=0.001)


def test_physical_pair_with_a_different_catalogue_is_rejected():
    refs = {r["id"]: r for r in charts.corpus.references("transfer124")}
    binding = charts._frozen_bindings(refs)[0]
    method = "point_votes"
    directory, release = charts.cold_missing.METHODS[method]
    correct = charts.read_predictions(charts.REPORT / directory / "matched-tile.jsonl.gz")
    omitted = charts.read_predictions(charts.REPORT / "wrong-tiles/point_votes.jsonl.gz")
    bad = dict(omitted[binding["id"]], catalog_sha256="different")
    with pytest.raises(ValueError, match="unmatched"):
        charts._check_physical_pair(correct[binding["id"]], bad, binding, method, release)


def test_each_receiver_gets_one_page_with_both_arms_and_audited_counts(tmp_path):
    assert charts.generate(tmp_path) == tmp_path / "README.md"
    for method in charts.TITLES:
        assert (tmp_path / f"{method}.png").read_bytes().startswith(b"\x89PNG")
    raw = (tmp_path / "modifications.pdf").read_bytes()
    assert len(re.findall(rb"/Type\s*/Page\b", raw)) == 3
    rows = list(csv.DictReader((tmp_path / "per-case.csv").read_text().splitlines()))
    assert len(rows) == 66
    summary = json.loads((tmp_path / "coverage.json").read_bytes())["groups"]
    assert len(summary) == 24
    published = [r for r in summary if r["published"]]
    assert {(r["method"], r["cohort"], r["arm"]) for r in published} == {
        ("folded_doppler", "correct", arm) for arm in charts.ARMS
    }
    for r in published:
        assert (r["published"], r["withheld"], r["attempts"]) == (1, 2, 3)
        assert r["error_km"]["p50"] == pytest.approx(6.378, abs=0.002)
    for r in summary:
        assert r["attempts"] == r["published"] + r["withheld"] + r["other_outcomes"]
