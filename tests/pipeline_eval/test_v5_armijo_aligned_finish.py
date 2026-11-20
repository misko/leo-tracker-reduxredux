import json
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import armijo_finish_phase_retry
from tools.pipeline_eval.scoring import ARMS
from tools.pipeline_eval.variants import v5_armijo_aligned_finish, v5_armijo_finish


def install(monkeypatch, context, remap):
    module = ModuleType("leo.analysis.localization_v3")
    module.reassociation_context = context
    module.reassociation_recovery = SimpleNamespace(remap=remap)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return module.reassociation_recovery


def test_equal_length_reassociation_is_identity_without_any_addition(monkeypatch, tmp_path):
    monkeypatch.setattr(armijo_finish_phase_retry, "LOCK", tmp_path / "no-prior-diagnostic-lock")
    context = dict(
        scan=SimpleNamespace(norads=[1911, 6242]),
        node=dict(seed=dict(state=dict(phases=np.array([0.05, 0.8])))),
    )
    received = []

    def remap(candidate, hypothesis, ledger):
        received.append(candidate)
        return candidate

    recovery = install(monkeypatch, SimpleNamespace(add_target=lambda *args: None), remap)

    def finish(request, result, library):
        assert recovery.remap(context, {"name": "arbitrary"}, {}) is context
        result.write_text('{"status":"ok","metrics":{}}')

    monkeypatch.setattr(v5_armijo_finish, "worker", finish)
    target = tmp_path / "positions.json"
    v5_armijo_aligned_finish.worker("request", target, "library")
    result = json.loads(target.read_text())
    assert received == [context]
    assert result["metrics"]["ordered_phase_seeds"] == dict(aligned=[], equal_length=1)


@pytest.mark.parametrize("retains_prefix", [True, False])
def test_guard_uses_only_the_live_adopted_identity(monkeypatch, tmp_path, retains_prefix):
    starts = np.array([0.01, -0.98])
    seed = dict(state=dict(phases=starts), rows=[dict(candidate_index=1, candidate_norad=620)])
    state = dict(
        scan=SimpleNamespace(norads=[315, 620]),
        node=dict(seed=seed),
        means=np.array([0.4]),
        problems={
            a: (SimpleNamespace(reference=np.array([-0.25]), labels=[1]), None) for a in ARMS
        },
    )

    def addition(context):
        prefix = context["scan"].norads if retains_prefix else context["scan"].norads[::-1]
        context["scan"] = SimpleNamespace(norads=[*prefix, 2013])
        return dict(norad=2013, candidate_index=2)

    def remap(context, hypothesis, ledger):
        np.testing.assert_array_equal(
            context["node"]["seed"]["state"]["phases"], [0.01, -0.98, 0.0]
        )
        assert context["means"] is state["means"] and context["problems"] is state["problems"]
        return context

    residual = SimpleNamespace(add_target=addition)
    recovery = install(monkeypatch, residual, remap)

    def finish(request, result, library):
        residual.add_target(state)
        recovery.remap(state, {"name": "arbitrary"}, {})
        result.write_text('{"status":"ok","metrics":{}}')

    monkeypatch.setattr(v5_armijo_finish, "worker", finish)
    target = tmp_path / "positions.json"
    if not retains_prefix:
        with pytest.raises(ValueError, match="changed the ordered sky identities"):
            v5_armijo_aligned_finish.worker("request", target, "library")
        return
    v5_armijo_aligned_finish.worker("request", target, "library")
    result = json.loads(target.read_text())
    assert result["metrics"]["ordered_phase_seeds"] == dict(
        aligned=[
            dict(hypothesis="arbitrary", added_norad=2013, catalogue_index=2, initializer_seconds=0)
        ],
        equal_length=0,
    )
    np.testing.assert_array_equal(starts, [0.01, -0.98])
