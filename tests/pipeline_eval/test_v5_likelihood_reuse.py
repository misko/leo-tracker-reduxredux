from types import SimpleNamespace

import numpy as np
import pytest
from numpy.testing import assert_array_equal

from tools.pipeline_eval.qualification.likelihood_reuse_eval import arms_summary, decision
from tools.pipeline_eval.variants.v5_likelihood_reuse import EndpointReuse, exact_value


class Bound:
    def __init__(self):
        self.calls = 0

    def __call__(self, observation, design, *, weights, model=0.0):
        self.calls += 1
        return {
            "coefficient": observation + design[:, 0] + weights,
            "predictions": [{"sign": bool(np.signbit(model))}],
        }


class Model:
    def __init__(self):
        self.scan = SimpleNamespace(bound=Bound())
        self.observation = np.array([1.0, 2.0])
        self.design = np.array([[2.0], [3.0]])
        self.weights = np.array([7.0, 9.0])
        self.model = 0.0

    def calculate(self, coordinate):
        return self.scan.bound(
            self.observation + coordinate, self.design, weights=self.weights, model=self.model
        )


@pytest.fixture
def reuse():
    cache = EndpointReuse()
    try:
        yield cache
    finally:
        cache.clear()


def test_native_cache_keeps_a_private_result_on_miss_and_hit(reuse):
    model = Model()
    point = np.array([0.75, 0.125])
    operation = model.scan.bound
    expected = model.calculate(point)
    reuse.bind(model, point, "retained")
    first = model.calculate(point.copy())
    first["coefficient"] *= 4
    first["predictions"][0]["sign"] = True
    hit = model.calculate(point.copy())
    assert_array_equal(hit["coefficient"], expected["coefficient"])
    assert hit["predictions"] == expected["predictions"]
    hit["coefficient"][:] = 4
    hit["predictions"].clear()
    repeated = model.calculate(point.copy())
    assert_array_equal(repeated["coefficient"], expected["coefficient"])
    assert repeated["predictions"] == expected["predictions"]
    assert model.scan.bound is operation
    assert operation.calls == 2
    assert reuse.statistics["retained"]["hits"] == 2


@pytest.mark.parametrize("attribute", ("observation", "design", "weights"))
def test_writable_aliases_invalidate_bound_arguments(reuse, attribute):
    model = Model()
    operation = model.scan.bound
    point = np.zeros(2)
    reuse.bind(model, point, "history")
    original = model.calculate(point)
    np.asarray(getattr(model, attribute)).reshape(-1)[0] += 4
    changed = model.calculate(point)
    reused_change = model.calculate(point)
    assert changed["coefficient"][0] == original["coefficient"][0] + 4
    assert_array_equal(changed["coefficient"], reused_change["coefficient"])
    assert operation.calls == 2
    assert reuse.statistics["history"]["hits"] == 1


def test_backend_and_model_changes_clear_reuse_and_restore_original(reuse):
    model = Model()
    operation = model.scan.bound
    point = np.zeros(2)
    reuse.bind(model, point, "retained")
    model.calculate(point)
    model.calculate(point)
    model.scan.bound = Bound()
    model.calculate(point)
    assert operation.calls == 1
    assert model.scan.bound.calls == 1

    same_input = Model()
    same_input.scan = model.scan
    reuse.bind(same_input, point, "retained")
    assert "calculate" not in model.__dict__
    same_input.calculate(point)
    assert model.scan.bound.calls == 2
    assert reuse.statistics["retained"]["models"] == 2
    reuse.clear()
    assert "calculate" not in same_input.__dict__
    assert reuse.previous is None


def test_nonendpoint_calls_and_distinct_scalar_bits_are_not_reused(reuse):
    model = Model()
    point = np.array([0.0, 0.0])
    reuse.bind(model, point, "predictive")
    assert not model.calculate(point)["predictions"][0]["sign"]
    off = np.array([-0.0, 0.0])
    model.calculate(off)
    model.calculate(off)
    model.model = -0.0
    assert model.calculate(point)["predictions"][0]["sign"]
    assert model.calculate(point)["predictions"][0]["sign"]
    assert model.scan.bound.calls == 4
    assert exact_value(0.0) != exact_value(-0.0)
    assert exact_value(np.array([0], dtype=np.int32)) != exact_value(np.array([0], dtype=np.int64))
    assert exact_value(np.array([0, 0])) != exact_value(np.array([[0, 0]]))


def test_failed_and_unsupported_inputs_use_native_operation(reuse):
    model = Model()
    calls = []

    def native(*args, **kwargs):
        calls.append(kwargs["model"])
        if kwargs["model"] is None:
            raise ValueError("native error")
        return {"coefficient": np.ones(2)}

    model.scan.bound = native
    point = np.zeros(2)
    reuse.bind(model, point, "history")
    model.calculate(point)
    model.model = None
    with pytest.raises(ValueError, match="native error"):
        model.calculate(point)
    assert model.scan.bound is native
    model.model = 0.0
    model.calculate(point)
    model.model = []
    model.calculate(point)
    model.calculate(point)
    assert calls == [0.0, None, 0.0, [], []]


def test_instrumented_stock_never_reuses_a_result():
    stock = EndpointReuse(enabled=False)
    model = Model()
    point = np.zeros(2)
    try:
        stock.bind(model, point, "history")
        first = model.calculate(point)
        assert_array_equal(first["coefficient"], model.calculate(point)["coefficient"])
        result = stock.statistics["history"]
        assert model.scan.bound.calls == result["solves"] == result["calls"] == 2
        assert result["hits"] == 0
        assert stock.previous is None
    finally:
        stock.clear()


def test_history_and_conservative_track_admissions_enter_decision_receipt():
    gate = dict(
        component="scan-a",
        candidate_index=21,
        aliases_changed=0,
        compatible=True,
        points=2,
        observation_ids=[12, 14],
    )
    retained = {"tracks": [gate], "accepted_points": 2}
    summary = {"c0": {"gates": retained}}
    assert arms_summary(summary)["c0"]["curved"] == [gate]
    assert arms_summary({"c0": {"metrics": retained}}) == arms_summary(summary)
    conservative = {"final_node": {"seed": {"rows": [gate]}, "aliases": [3]}, "arms": summary}
    picked = decision("conservative_recovery", conservative)
    assert picked["aliases"] == [3]
    assert picked["selected"][0]["candidate_index"] == 21
    assert picked["arms"]["c0"]["accepted_points"] == 2
