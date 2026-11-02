"""Frozen-source parity and component-owned guards for ALGO07 numerical code."""
import ast
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.special import logsumexp

from algo07_science import diagnose, engine, policy, predictive, propagation, uniqueness, validation
from leo.analysis.research.retained_track_likelihood import PERIOD


REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "tools/algo07_science"
MANIFEST = json.loads((PACKAGE / "origin_manifest.json").read_text())


def function_source(path, name):
    text = path.read_text()
    node = next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(text, node)


def normalized(code):
    def encode(node):
        if isinstance(node, ast.AST):
            return [type(node).__name__, [[key, encode(value)] for key, value in ast.iter_fields(node)
                                         if value is not None and value != []]]
        if isinstance(node, list):
            return [encode(value) for value in node]
        return node
    return json.dumps(encode(ast.parse(code)), separators=(",", ":"))


@pytest.mark.parametrize("origin", MANIFEST["functions"], ids=lambda r: r["module"] + ":" + r["function"])
def test_frozen_function_ast_and_source_hashes(origin):
    source = REPO / origin["source"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == origin["source_file_sha256"]
    original = function_source(source, origin["function"])
    assert hashlib.sha256(normalized(original).encode()).hexdigest() == origin["source_ast_sha256"]
    for substitution in origin["substitutions"]:
        assert substitution["before"] in original
        original = original.replace(substitution["before"], substitution["after"])
    port = function_source(PACKAGE / origin["module"], origin["function"])
    assert normalized(port) == normalized(original)
    assert hashlib.sha256(normalized(port).encode()).hexdigest() == origin["port_ast_sha256"]


def oracle(module, name):
    """Execute only the frozen function AST, never import research drivers."""
    entry = next(r for r in MANIFEST["functions"] if r["module"] == module and r["function"] == name)
    namespace = dict(np=np, logsumexp=logsumexp, PERIOD=PERIOD, SEED=validation.SEED)
    exec(function_source(REPO / entry["source"], name), namespace)
    return namespace[name]


def test_normalized_predictive_scores_match_frozen_oracles_and_train_only_aliases():
    rng = np.random.default_rng(123)
    t = np.tile(np.arange(0., 150., .5), 2)
    groups = np.repeat(np.arange(2), 300)
    rx = groups + 1
    q = np.where(groups == 0, .94, 1.02)
    phase = np.linspace(-30., 30., 151)
    raw = rng.normal(0., 130., (len(phase), len(t))) + phase[:, None] * 2 + groups * PERIOD
    split = validation.partitions(t, groups)[0]
    arguments = (raw, t, q, groups, split["train"], split["test"], phase)
    assert predictive.fit_predict(*arguments) == oracle("predictive.py", "fit_predict")(*arguments)
    modified = raw.copy()
    modified[:, split["test"]] += 2e5
    changed = predictive.fit_predict(modified, *arguments[1:])
    original = predictive.fit_predict(*arguments)
    assert changed["training_score"] == original["training_score"]
    assert changed["alias_by_group"] == original["alias_by_group"]
    assert changed["predictive_score"] != original["predictive_score"]
    for model in ("track_offset", "receiver_offset", "frozen_radio"):
        args = (raw, t, q, groups, rx, split["train"], split["test"], phase, model, 5.)
        observed = validation.predict(*args)
        expected = oracle("validation.py", "predict")(*args)
        np.testing.assert_array_equal(observed.pop("coefficient"), expected.pop("coefficient"))
        assert observed == expected


def test_random_whole_group_holdouts_preserve_seed_guards_and_uniqueness():
    t = np.tile(np.arange(0., 150., .5), 2)
    groups = np.repeat(np.arange(2), 300)
    a = validation.partitions(t, groups)
    b = oracle("validation.py", "partitions")(t, groups)
    assert len(a) == 10
    assert len({tuple(r["held_blocks"]) for r in a}) == 10
    for left, right in zip(a, b, strict=True):
        for key in left:
            np.testing.assert_array_equal(left[key], right[key])
        blocks = np.floor(t / 5).astype(int)
        assert not left["train"][np.isin(blocks, left["guard_blocks"])].any()
        assert not np.any(left["train"] & left["test"])


def test_derivatives_reproduce_frozen_numerical_operations():
    fun = lambda x: float(x @ np.array([[2., .2], [.2, 3.]]) @ x + x[0] ** 3)
    point = np.array([1.3, -.4])
    got = diagnose.derivatives(fun, point)
    expected = oracle("diagnose.py", "derivatives")(fun, point)
    for actual, frozen in zip(got, expected, strict=True):
        np.testing.assert_array_equal(actual, frozen)
    assert diagnose.error(point) is None
    assert engine.previous.error(point) is None


def test_all_reconstruction_hooks_use_the_same_frozen_builder(tmp_path, monkeypatch):
    for name in ("OUT", "ROOTS", "collect_history"):
        monkeypatch.setattr(engine, name, getattr(engine, name))
    monkeypatch.setattr(engine.rec, "CATALOGUES", engine.rec.CATALOGUES)
    monkeypatch.setattr(engine.rec.ex, "PRIOR", engine.rec.ex.PRIOR)
    callback = lambda request: {"chosen": {}, "request": request}
    engine.configure(tmp_path / "input", tmp_path / "output", collect_history=callback)
    assert engine.ROOTS == {"SCAN": tmp_path / "input"}
    assert engine.rec.CATALOGUES == tmp_path / "input/catalogues"
    assert engine.collect_history({"cutoff": 1})["chosen"] == {}
    assert engine.rec.build is diagnose.build is engine.previous.build is engine.rec.ex.ORIGINAL_BUILD is engine.build


def test_real_remap_preserves_unselected_native_tracks_in_both_arms(tmp_path, monkeypatch):
    from algo07_science import experiment
    assert experiment.ARMS == engine.ARMS
    monkeypatch.setattr(experiment, "PRIOR", tmp_path)
    case = "SCAN"
    experiment_path = tmp_path / case / "tle-ledger.json"
    experiment_path.parent.mkdir()
    experiment_path.write_text(json.dumps({"causal": {}}))
    rows = [dict(component="target", candidate_norad=1, candidate_index=0),
            dict(component="retained", candidate_norad=2, candidate_index=1)]
    old = SimpleNamespace(rows=copy.deepcopy(rows), labels=[0, 1], reference=np.array([3., 4.]))
    d = dict(scan=SimpleNamespace(norads=np.array([1, 2, 3])),
             node=dict(seed=dict(rows=copy.deepcopy(rows)), aliases=[0, 0]),
             entries=[dict(component="target", norad=1, candidate_index=0),
                      dict(component="retained", norad=2, candidate_index=1)],
             means=np.array([.1, .2]), problems={a: (old, np.zeros(2)) for a in engine.ARMS})
    calls = []
    def build(context, z, arm, reference):
        calls.append((arm, reference.copy()))
        return SimpleNamespace(reference=reference), context
    monkeypatch.setattr(experiment, "ORIGINAL_BUILD", build)
    hypothesis = dict(mapping={"target": 3}, aliases={"target": 5}, phases={"3": 6.})
    result = experiment.remap(d, {}, case, hypothesis)
    assert [arm for arm, _ in calls] == list(engine.ARMS)
    for _, reference in calls:
        np.testing.assert_array_equal(reference, [4., 6.])
    assert result["node"]["seed"]["rows"][0]["candidate_norad"] == 3
    assert result["node"]["seed"]["rows"][1] == rows[1]
    assert result["entries"][0]["norad"] == 3
    assert result["entries"][1] == d["entries"][1]
    assert result["node"]["aliases"] == [5, 0]
    assert d["node"]["seed"]["rows"] == rows
    assert d["node"]["aliases"] == [0, 0]


def test_uniqueness_requires_every_competitor_on_every_unique_fold_and_both_arms():
    parts = [dict(fold=f, held_blocks=[f]) for f in range(5)]
    rows = [dict(arm=a, fold=f, norad=n, model="receiver_offset", phase_sd_s=5., predictive_score=float(n))
            for a in engine.ARMS for f in range(5) for n in (1, 2, 3)]
    assert uniqueness.conditional_uniqueness(rows, parts, [1, 2, 3], 1)["passed"]
    incomplete = uniqueness.conditional_uniqueness(rows[:-1], parts, [1, 2, 3], 1)
    assert incomplete["status"] == "not_evaluated"
    rows[0]["predictive_score"] = 3.
    assert not uniqueness.conditional_uniqueness(rows, parts, [1, 2, 3], 1)["passed"]
    assert not uniqueness.conditional_uniqueness(rows, [parts[0]] * 5, [1, 2, 3], 1)["passed"]


def test_policy_retains_baseline_on_incomplete_guard_and_does_not_consume_truth():
    baseline = {a: dict(associated=2) for a in engine.ARMS}
    fit = dict(qualified=True, all_gates_pass=True, phase_closed=True, optimizer_success=True,
               mixture_phase_interior=True, native_ids_sha256="same", lost_ids=[], unexpected_reassigned_ids=[],
               x=[1., 2.], error_m=None, objective=90., rms_hz=2.)
    row = dict(name="replacement", accepted=True, gains=dict.fromkeys(engine.ARMS, 10.),
               pair={a: copy.deepcopy(fit) for a in engine.ARMS},
               control={a: dict(native_ids_sha256="same") for a in engine.ARMS})
    guard = dict(passed=True, model="receiver_offset", unique_folds=5, missing=[], minimum_margin=1.)
    assert policy.select(baseline, [row], {})["final"] == baseline
    assert policy.select(baseline, [row], {"replacement": guard})["selected"] == "replacement"
    row["pair"]["c0"]["error_m"] = 1e100
    assert policy.select(baseline, [row], {"replacement": guard})["selected"] == "replacement"
    guard["minimum_margin"] = 0.
    assert policy.select(baseline, [row], {"replacement": guard})["selected"] is None


def test_propagation_classification_never_silently_drops_unknown_or_partial_failures():
    finite = np.ones((3, 3))
    for errors, expected in (([0, 0, 0], "eligible"),
                             ([1, 1, 1], "exclude_consistent_model_invalid_all_grid"),
                             ([0, 1, 1], "block_partial_grid_failure"),
                             ([5, 5, 5], "block_unknown_or_inconsistent_all_grid_failure"),
                             ([1, 2, 1], "block_unknown_or_inconsistent_all_grid_failure")):
        assert propagation.classify(errors, finite, finite) == expected
    bad = finite.copy()
    bad[0, 0] = np.nan
    assert propagation.classify([0, 0, 0], bad, finite) == "block_nonfinite_without_error"


def test_runtime_package_contains_no_report_imports_case_rosters_or_evaluation_coordinates():
    for path in PACKAGE.glob("*.py"):
        if path.name == "runner.py":
            continue
        source = path.read_text()
        assert "/home/mouse" not in source
        assert "DS26-" not in source
        assert "SITE_X" not in source
        assert "37.849061" not in source
        assert "sudo" not in source
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("reports")
            if isinstance(node, ast.Import):
                assert all(not n.name.startswith("reports") for n in node.names)
