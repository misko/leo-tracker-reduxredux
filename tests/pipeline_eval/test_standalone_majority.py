import ast
import inspect

import pytest

from tools.pipeline_eval.qualification import screening_figures
from tools.pipeline_eval.qualification import standalone_majority as trial
from tools.pipeline_eval.qualification import standalone_majority_results as results
from tools.pipeline_eval.scoring import ARMS


def test_executed_standalone_embeds_exact_frozen_predicate_and_winner_receipt():
    path = trial.REPORT / "as-executed-v5-direct-cavity.py.txt"
    text = path.read_text()
    assert inspect.getsource(trial.frozen.admits_recovery).rstrip() in text
    tree = ast.parse(text)
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in ("admits_recovery", "initial_support")
    ]
    namespace = {}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), "exec"), namespace)
    vote = namespace["initial_support"]
    rejected = dict(accepted_points=50, tracks=[{"points": 30}, {"points": 70}])
    accepted = dict(accepted_points=51, tracks=[{"points": 100}])
    case = dict(
        choices=[
            dict(hypothesis=i, arms={"c0": {"metrics": m}})
            for i, m in enumerate((rejected, accepted))
        ]
    )
    assert vote(dict(case, selected_hypothesis=0))["admitted"] is False
    assert vote(dict(case, selected_hypothesis=1))["admitted"] is True


def test_withholding_cannot_claim_a_position_or_later_stage():
    support = dict(accepted_points=5, tracked_points=12, admitted=False)
    row = dict(
        result=dict(
            reason=results.CUT,
            metrics=dict(initial_support=support),
            arms={a: {"latlon": None} for a in ARMS},
        ),
        runtime=dict(stage=[{"name": "initial_support"}]),
    )
    assert results.validate_stage(row) == support
    row["runtime"]["stage"].append({"name": "conservative_recovery"})
    with pytest.raises(ValueError, match="advanced"):
        results.validate_stage(row)


def test_charts_separate_primary_replay_and_archived_near_case():
    chart = {c.id: c for c in screening_figures.charts(evidence=trial.REPORT)}
    for name, n in (("primary", 4), ("archived-near", 1)):
        current = chart[f"standalone-majority-{name}"]
        assert len(current.cases) == n
        for arm in ARMS:
            for series in ("candidate", "stock"):
                assert len([r for r in current.page(arm).rows if r.series == series]) == n
