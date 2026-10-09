import copy
import runpy
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

HERE = Path(__file__).parent
api = runpy.run_path(str(HERE / "audit.py"))
fixture = runpy.run_path(str(HERE / "test_adapter.py"))["fixture"]
construct = runpy.run_path(str(HERE / "adapter.py"))["construct"]


def test_mocked_both_arm_pipeline_and_prior_distinction():
    model, endpoint, predictor = fixture()
    model.observations = NS(times_s=np.arange(3))
    model.bank = NS(numbers=np.arange(2))
    model.evaluate_joint = lambda v, c: (
        7,
        None,
        None,
        NS(responsibilities=np.full((3, 2), 0.25), residual_hz=np.full((3, 2), 20)),
    )
    endpoint["stage"] = "B7"
    zero = copy.deepcopy(endpoint)
    zero["vector"][6] = 0
    zero["clock_coefficients"][-2:] = 0
    archive = dict(stages=dict(B7={"fitted-c": endpoint, "zero-c": zero}))
    result = api["audit_model"](
        model, archive, adapter=lambda m, e, a: construct(m, e, a, predictor=predictor)
    )
    assert set(result["arms"]) == {"fitted-c", "zero-c"}
    for data in result["arms"].values():
        assert data["objective_delta"] == 0
        assert data["bounds_omitted"] and data["observed_schur_complement"] is None
        assert data["data_only"]["prior_information"] is None
        assert data["spatial_blocks"]["observed_local"].shape == (2, 2)
    assert result["arms"]["zero-c"]["locked_parameter_indices"] == [6, 12, 13]


def test_resource_guard_runs_before_adapter():
    model = NS(
        observations=NS(times_s=np.zeros(1000)),
        bank=NS(numbers=np.zeros(150)),
        size=160,
        initial_clock=np.zeros(30),
    )
    with pytest.raises(MemoryError):
        api["audit_model"](model, {}, adapter=lambda *a: pytest.fail("allocated before guard"))


def test_full_authority_retained_and_selection_exact():
    members = [dict(member=dict(inventory_label=f"M{i}")) for i in range(148)]
    plan = dict(potential_members=members, members=members[:12])
    assert api["selected_members"](plan, copy.deepcopy(plan)) == members[:12]
    altered = copy.deepcopy(plan)
    altered["members"][0] = members[13]
    with pytest.raises(AssertionError):
        api["selected_members"](altered, plan)


def test_failed_input_receipt_append_only(tmp_path):
    binding = dict(member=dict(inventory_label="synthetic"), b7_source="not-a-source")
    receipt = api["evaluate"](
        binding,
        "hash",
        read=lambda p: (_ for _ in ()).throw(ValueError("synthetic unavailable")),
        reconstruct=lambda *a: None,
        directory=tmp_path,
    )
    assert receipt["status"] == "failed" and "synthetic unavailable" in receipt["error"]
    assert api["evaluate"](binding, "hash", directory=tmp_path) == receipt
    with pytest.raises(AssertionError):
        api["evaluate"](binding, "wrong", directory=tmp_path)


def test_thread_checks_before_reconstruction():
    environment = {
        name: "1" for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
    }
    api["check_threads"](environment)
    for name in environment:
        changed = dict(environment)
        changed[name] = "2"
        with pytest.raises(ValueError, match=name):
            api["check_threads"](changed)
