"""Exact orchestration parity and read-only causal-history selection parity."""
import ast
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import algo07_history as history
from algo07_science import runner


REPO = Path(__file__).resolve().parents[2]
FROZEN_RUNNER = REPO / "reports/2026_11_01_promotion_readiness/run_candidate.py"
FROZEN_HISTORY = REPO / "reports/2026_11_01_ds26_reconsideration/read_history.py"


def function_source(path, name):
    source = path.read_text()
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(source, node)


def test_runner_source_and_frozen_io_metadata_substitutions_are_explicit():
    assert hashlib.sha256(FROZEN_RUNNER.read_bytes()).hexdigest() == "520aebb583f8ac087035f3dfb4d03e214f52c69507b16c0e246334b075f1af5a"
    # These substitutions change private input/history acquisition and retain
    # already-computed proof values. Numerical selection and fit calls are exact.
    replacements = {
        "score_record": [(
            "accepted=bool(complete and all(v>0 for v in gains.values())))",
            "accepted=bool(complete and all(v>0 for v in gains.values())),bounds=bounds)",
        )],
        "run_worker": [(
            "began=time.monotonic();protocol=verify_frozen(input_root,output_root,case)\n    configure(input_root,output_root)",
            "began=time.monotonic()\n    if case != 'SCAN':raise ValueError('Private single-scan input required')\n    from algo07_history import collect_private\n    e.configure(input_root,output_root,collect_history=lambda request: collect_private(input_root/'history-bank.json',request))\n    protocol=read(output_root/'protocol.json')",
        ), (
            "bounds={a:min(controls[a]['objective'],baseline[a]['objective'],\n                       e.objective(hd['problems'][a][0],hd,d['problems'][a][1])) for a in e.ARMS} if all(controls.values()) else {}",
            "matched_published={a:e.objective(hd['problems'][a][0],hd,d['problems'][a][1]) for a in e.ARMS} if all(controls.values()) else {}\n        bounds={a:min(controls[a]['objective'],baseline[a]['objective'],matched_published[a]) for a in e.ARMS} if all(controls.values()) else {}",
        ), (
            "record.update(target=old,history=hinfo,fits_path=str(trial/'fits.json'))",
            "record.update(target=old,history=hinfo,fits_path=str(trial/'fits.json'),matched_published_objectives=matched_published)",
        )],
    }
    names = ("read", "sha", "write", "published_baseline", "public_owners", "preflight_public",
             "destination_owned", "score_record", "fallback", "fit_rows_complete", "propagation_eligible", "run_worker")
    for name in names:
        source = function_source(FROZEN_RUNNER, name)
        for before, after in replacements.get(name, []):
            assert before in source
            source = source.replace(before, after)
        actual = function_source(REPO / "tools/algo07_science/runner.py", name)
        assert ast.dump(ast.parse(source), include_attributes=False) == ast.dump(ast.parse(actual), include_attributes=False), name


def fit(score=80.):
    return dict(x=[0., 0.], error_m=None, objective=score, rms_hz=12., qualified=True, all_gates_pass=True,
                phase_closed=True, optimizer_success=True, mixture_phase_interior=True, lost_ids=[],
                unexpected_reassigned_ids=[], native_ids_sha256="same", status="complete")


@pytest.mark.parametrize("candidate_score,control_score,penalty", [(80., 100., 2.), (99., 100., 2.), (-10., 0., 0.)])
def test_paired_penalized_scores_match_frozen_runner(candidate_score, control_score, penalty):
    namespace = {"e": runner.e}
    exec(function_source(FROZEN_RUNNER, "score_record"), namespace)
    hypothesis = dict(name="replacement", penalty=penalty)
    pair = {a: fit(candidate_score) for a in runner.e.ARMS}
    control = {a: fit(control_score) for a in runner.e.ARMS}
    bounds = dict.fromkeys(runner.e.ARMS, control_score)
    actual = runner.score_record(hypothesis, pair, control, bounds)
    assert actual.pop("bounds") == bounds
    assert actual == namespace["score_record"](hypothesis, pair, control, bounds)
    control["c0"] = None
    assert not runner.score_record(hypothesis, pair, control, {})["accepted"]


def worker_context(monkeypatch, guard_pass=True):
    baseline = {a: dict(x=[0., 0.], error_m=None, objective=100., associated=1, rms_hz=None) for a in runner.e.ARMS}
    monkeypatch.setattr(runner.e, "configure", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "sha", lambda *args: "hash")
    d = dict(problems={a: (None, np.zeros(2)) for a in runner.e.ARMS})
    z = dict(baseline_owners={a: {"obs": 10} for a in runner.e.ARMS}, scan_receipt={"origin_utc_ns": 0})
    monkeypatch.setattr(runner.e, "load_case", lambda case: (d, z, {}))
    monkeypatch.setattr(runner.e, "objective", lambda *args: 100.)
    monkeypatch.setattr(runner, "preflight_public", lambda *args: {"public_owner_maps_equal": True})
    monkeypatch.setattr(runner, "read", lambda path: dict(baselines={"SCAN": baseline}))
    monkeypatch.setattr(runner.e.rec, "causal_records", lambda *args: {"10": {}, "20": {}})
    monkeypatch.setattr(runner.e, "rank_families", lambda *args: ([], [10]))
    monkeypatch.setattr(runner.e.rec, "bank_for", lambda *args: ([10, 20], dict(position_km=np.zeros((2, 2, 3)), velocity_km_s=np.zeros((2, 2, 3))), []))
    monkeypatch.setattr(runner, "audit_catalogue", lambda *args: dict(failures=[], nominal_causality_verified=True, partial_or_unknown_blocks=[]))
    h = dict(name="10_to_20", norad=20, mapping={"track": 20}, allowed_families=[10, 20], penalty=2.,
             predictive={a: dict(pass_check=True) for a in runner.e.ARMS})
    screen = dict(proposals=[h], cavity={"fitted_c": {"x": [1., 1.]}})
    monkeypatch.setattr(runner.e.rec, "screen", lambda *args: screen)
    monkeypatch.setattr(runner, "receiver_shared_check", lambda *args: {"new": 20})
    guard = dict(passed=guard_pass, model="receiver_offset", unique_folds=5, missing=[], minimum_margin=1.)
    monkeypatch.setattr(runner, "from_additional_checks", lambda *args: guard)
    return baseline, d, z


def test_rejected_predictive_guard_does_not_collect_history_or_refit(monkeypatch, tmp_path):
    baseline, _, _ = worker_context(monkeypatch, False)
    def forbidden(*args, **kwargs):
        raise AssertionError("History/refit before predictive admission")
    monkeypatch.setattr(runner.e, "complete_history", forbidden)
    monkeypatch.setattr(runner.e, "fit_rows", forbidden)
    result = runner.run_worker("SCAN", tmp_path / "input", tmp_path / "output")
    assert result["selected"] is None and result["final"] == baseline
    assert result["history"] is None


def test_admitted_joint_fit_uses_identical_starts_and_bounds_both_arms(monkeypatch, tmp_path):
    baseline, _, _ = worker_context(monkeypatch)
    requests = []
    monkeypatch.setattr(runner.e, "active_ids", lambda *args: {10})
    monkeypatch.setattr(runner.e, "complete_history", lambda context, z, case, identities, path:
                        (requests.append(set(identities)) or context, dict(changed=True)))
    monkeypatch.setattr(runner.e, "remap", lambda context, *args: context)
    def fit_rows(context, z, starts, allowed, path):
        assert list(starts) == ["published", "family_omitted"]
        np.testing.assert_array_equal(starts["published"], [0., 0.])
        np.testing.assert_array_equal(starts["family_omitted"], [1., 1.])
        return [dict(fit(80. if allowed else 100.), arm=a, start=s) for a in runner.e.ARMS for s in starts]
    monkeypatch.setattr(runner.e, "fit_rows", fit_rows)
    result = runner.run_worker("SCAN", tmp_path / "input", tmp_path / "output")
    assert requests == [{10}, {20}]
    assert result["selected"] == "10_to_20"
    record = result["records"][0]
    assert record["gains"] == {"c0": 18., "fitted_c": 18.}
    assert record["bounds"] == record["matched_published_objectives"] == {"c0": 100., "fitted_c": 100.}
    assert result["final"]["c0"]["associated"] == baseline["c0"]["associated"]


@pytest.mark.parametrize("incomplete_stage", ["control", "candidate"])
def test_any_incomplete_start_forces_exact_baseline(monkeypatch, tmp_path, incomplete_stage):
    baseline, _, _ = worker_context(monkeypatch)
    monkeypatch.setattr(runner.e, "active_ids", lambda *args: {10})
    monkeypatch.setattr(runner.e, "complete_history", lambda context, *args: (context, dict(changed=False)))
    monkeypatch.setattr(runner.e, "remap", lambda context, *args: context)
    def rows(context, z, starts, allowed, path):
        result = [dict(fit(), arm=a, start=s) for a in runner.e.ARMS for s in starts]
        if (bool(allowed) and incomplete_stage == "candidate") or (not allowed and incomplete_stage == "control"):
            result[0]["status"] = "incomplete"
        return result
    monkeypatch.setattr(runner.e, "fit_rows", rows)
    result = runner.run_worker("SCAN", tmp_path / "input", tmp_path / "output")
    assert result["execution_status"] == "incomplete_fit_fallback"
    assert result["selected"] is None and result["final"] == baseline


def test_unexplained_catalogue_failure_blocks_screening(monkeypatch, tmp_path):
    baseline, _, _ = worker_context(monkeypatch)
    monkeypatch.setattr(runner.e.rec, "bank_for", lambda *args: ([10], None, [20]))
    def forbidden(*args, **kwargs):
        raise AssertionError("Incomplete catalogue must not be screened")
    monkeypatch.setattr(runner.e.rec, "screen", forbidden)
    result = runner.run_worker("SCAN", tmp_path / "input", tmp_path / "output")
    assert result["execution_status"] == "propagation_fallback"
    assert result["selected"] is None and result["final"] == baseline


def test_private_history_selection_matches_original_request_collector(monkeypatch, tmp_path):
    assert hashlib.sha256(FROZEN_HISTORY.read_bytes()).hexdigest() == "9d0af36b26ffa98787cc2933a990ce305c5b9efc4f17a95f5ab8680dc5d33e13"
    cutoff = 400_000_000_000_000
    latest = {"1": cutoff-5_000_000_000, "2": cutoff-3_000_000_000, "3": cutoff}
    snapshots = [SimpleNamespace(collected_utc_ns=cutoff+1, digest="future_collection"),
                 SimpleNamespace(collected_utc_ns=cutoff-int(72*3.6e12)-1, digest="old_collection"),
                 SimpleNamespace(collected_utc_ns=cutoff-10, digest="first"),
                 SimpleNamespace(collected_utc_ns=cutoff-5, digest="second")]
    elements = {
        "future_collection": [(1, cutoff-7_000_000_000)],
        "old_collection": [(1, cutoff-7_000_000_000)],
        "first": [(1, cutoff-20_000_000_000), (1, cutoff-6_000_000_000), (2, cutoff-4_000_000_000),
                  (1, cutoff+1), (2, cutoff-3_500_000_000), (99, cutoff-10_000_000_000)],
        "second": [(1, cutoff-6_000_000_000), (2, cutoff-8_000_000_000)],
    }
    class Reader:
        def list_snapshots(self, provider):
            assert provider == "space-track"
            return snapshots
        def read(self, snapshot):
            return snapshot.digest
    reader = Reader()
    def parse(text):
        return [SimpleNamespace(satellite_number=n, text=f"1 {n}\n2 {epoch}") for n, epoch in elements[text]]
    def satrec(first, second):
        epoch = int(second.split()[1])
        return SimpleNamespace(jdsatepoch=2440587.5, jdsatepochF=epoch/86400e9)
    from sgp4 import api
    from leo.sky import propagation
    monkeypatch.setattr(api, "Satrec", SimpleNamespace(twoline2rv=satrec))
    monkeypatch.setattr(propagation, "parse_element_set_records", parse)
    namespace = dict(TleArchiveReader=lambda path: reader, Path=Path, Satrec=api.Satrec, parse_element_set_records=parse)
    exec(function_source(FROZEN_HISTORY, "collect"), namespace)
    expected = namespace["collect"](cutoff, latest)
    bank = history.collect_versions(cutoff, reader=reader)
    path = tmp_path / "history.json"
    path.write_text(json.dumps(bank))
    actual = history.collect_private(path, dict(cutoff=cutoff, latest=latest))
    assert actual == expected
    assert actual["chosen"]["1"]["digest"] == "first"
    assert set(actual["chosen"]) == {"1", "2"}
    assert actual["snapshot_count"] == 2
    with pytest.raises(ValueError, match="cutoff mismatch"):
        history.collect_private(path, dict(cutoff=cutoff+1, latest=latest))
    corrupt = copy.deepcopy(bank)
    corrupt["versions"]["1"][0]["collected_utc_ns"] = cutoff+1
    path.write_text(json.dumps(corrupt))
    with pytest.raises(ValueError, match="Noncausal"):
        history.collect_private(path, dict(cutoff=cutoff, latest=latest))
