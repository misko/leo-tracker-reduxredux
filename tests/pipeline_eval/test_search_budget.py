import json
import sys
from collections import Counter
from types import SimpleNamespace

import pytest

from tools.pipeline_eval.__main__ import encoded, read_predictions
from tools.pipeline_eval.qualification import initial_branch_audit as audit
from tools.pipeline_eval.qualification import search_budget as trial
from tools.pipeline_eval.scoring import ARMS
from tools.pipeline_eval.variants import v5_search_budget as receiver


def test_single_seed_uses_one_neutral_proposal_and_never_runs_the_corner_search(monkeypatch):
    scan = SimpleNamespace(radio_sigma_hz=5)
    seed = {"aliases": [2], "seed": {"rows": [1], "state": "warm"}}
    calls = []

    def discover(context, sigma, *, budget):
        assert context is scan
        calls.append((sigma, budget))
        return [seed]

    monkeypatch.setitem(
        sys.modules,
        "leo.analysis.localization_v3.discovery",
        SimpleNamespace(fresh_discovery=discover, zero_state=lambda context: "zero"),
    )
    monkeypatch.setattr(receiver.v5_core, "fit_initial_nodes", lambda context, nodes: nodes)
    monkeypatch.setattr(receiver.v5_core, "ranked_initial_nodes", lambda *_: pytest.fail("ranked"))
    assert receiver.one_seed(scan) == [{"aliases": [2], "seed": {"rows": [1], "state": "zero"}}]
    assert calls == [(5, 1)] and seed["seed"]["state"] == "warm"


def test_ranked_policy_keeps_only_the_first_already_sorted_node(monkeypatch):
    ranked = [object(), object(), object(), object()]
    monkeypatch.setattr(receiver.v5_core, "ranked_initial_nodes", lambda scan: ranked)
    monkeypatch.setattr(receiver.v5_core, "fit_initial_nodes", lambda context, nodes: nodes)
    assert receiver.first_ranked(object()) == ranked[:1]


def test_only_an_authenticated_chosen_branch_is_decoded():
    choices = encoded(["list", [["map", [["hypothesis", i]]] for i in (0, 1)]])
    raw = audit.CHOICES + choices + b"]," + audit.SELECTED + b"1],"
    assert audit.read_choices(raw) == ([{"hypothesis": 0}, {"hypothesis": 1}], 1)
    for bad in (raw + raw, raw.replace(b"false", b"true"), raw[:-3] + b"2],", raw[:-3] + b"true],"):
        with pytest.raises(ValueError):
            audit.read_choices(bad)


def test_archived_initial_points_reproduce_both_arms_and_the_nonwinning_starts():
    directory = trial.REPORT / "initial-checkpoints"
    receipt = json.loads((directory / "receipt.json").read_text())
    rosters = [
        read_predictions(directory / f"{method}.jsonl.gz") for method in (audit.RANKED, audit.STOCK)
    ]
    ranked, stock = rosters
    assert sorted(ranked) == sorted(stock) == receipt["cases"]
    assert len(ranked) == 135
    agreements = Counter()
    for case, record in ranked.items():
        control = stock[case]
        assert all(
            record[k] == control[k]
            for k in ("source_archive_sha256", "input_sha256", "native_sha256", "catalog_sha256")
        )
        metrics = record["result"]["metrics"]
        assert metrics["cold_rank"] == 0
        assert metrics["center_scores"] == sorted(metrics["center_scores"])
        losses = metrics["refreshed_c0_objectives"]
        assert losses.index(min(losses)) == metrics["winning_rank"]
        assert set(record["result"]["arms"]) == set(ARMS)
        if metrics["winning_rank"] == 0:
            assert control["result"]["arms"] == record["result"]["arms"]
            agreements[case.split("-")[0]] += 1
    assert agreements == {"DS26": 97, "DS29": 7}


def test_distribution_keeps_withheld_cases_and_single_record_regressions():
    def row(case, method, error, rms, elapsed):
        return dict(
            recording=case,
            dataset="DS26",
            method=method,
            arm="c0",
            status="ok" if error is not None else "withheld",
            position_error_km=error,
            v5_error_km=1,
            conditional_rms_hz=rms,
            initial_s=1,
            wall_s=elapsed,
        )

    rows = [
        row("A", "orbit_projector", 1, 100, 10),
        row("B", "orbit_projector", 1, 100, 20),
        row("A", "v5_first_ranked", 1.06, 80, 5),
        row("B", "v5_first_ranked", None, None, 1),
    ]
    by_method = {r["method"]: r for r in trial.distribution_rows(rows) if r["dataset"] == "all"}
    assert by_method["orbit_projector"]["passes_10pct_gate"]
    candidate = by_method["v5_first_ranked"]
    assert not candidate["passes_10pct_gate"]
    assert (candidate["published"], candidate["scheduled"]) == (1, 2)
    assert (candidate["paired_at_most_105pct_v5"], candidate["paired_at_most_110pct_v5"]) == (0, 1)
    assert (candidate["speed_pairs"], candidate["median_paired_worker_speedup"]) == (1, 2)
    assert candidate["median_conditional_rms_hz"] == 80


def test_scoring_rebuilds_the_measured_cohort_and_rejects_crossed_detector_inputs(tmp_path):
    runs = tmp_path / "runs"
    for method in trial.METHODS:
        filename = f"{method}.jsonl.gz"
        for case, row in read_predictions(trial.REPORT / filename).items():
            directory = runs / case
            directory.mkdir(exist_ok=True, parents=True)
            (directory / f"{method}.json").write_bytes(encoded(row))
    output = tmp_path / "verified"
    trial.package(runs, output)
    for name in ("distributions.csv", "per-recording.csv", "receipt.json"):
        assert (output / name).read_bytes() == (trial.REPORT / name).read_bytes()

    changed = runs / trial.TIMING_IDS[-1] / "orbit_projector.json"
    row = json.loads(changed.read_text())
    row["native_sha256"] = "0" * 64
    changed.write_bytes(encoded(row))
    with pytest.raises(ValueError, match="mismatched input"):
        trial.package(runs, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()
