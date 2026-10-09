import copy
import json
import runpy
from pathlib import Path

import numpy as np
import pytest

api = runpy.run_path(str(Path(__file__).with_name("report.py")))


def fixture():
    member = dict(inventory_label="synthetic", dataset="DS16")
    data = dict(
        raw=dict(singular_values=[3, 2], rank=2),
        projected=dict(singular_values=[1, 0], rank=1),
        nuisance_rank=3,
    )
    arm = dict(
        data_only=data,
        spatial_block_eigenvalues=dict(observed_local=[-1, 2]),
        spatial_blocks=dict(
            complete=np.eye(2).tolist(), missing_information=(np.eye(2) * 0.5).tolist()
        ),
    )
    receipt = dict(
        member=member,
        protocol_sha256="hash",
        status="complete",
        elapsed_s=2,
        arms={a: copy.deepcopy(arm) for a in ("fitted-c", "zero-c")},
    )
    return dict(members=[dict(member=member)], potential_members=[{}] * 148), dict(
        synthetic=receipt
    )


def test_known_distributions_and_negative_curvature():
    plan, receipts = fixture()
    s = api["summarize"](plan, receipts, "hash")
    assert s["metrics"]["fitted-c"]["projected"]["ranks"]["1"] == 1
    assert s["metrics"]["zero-c"]["fixed_nuisance_observed"]["negative_eigenvalue_records"] == 1
    assert (
        s["metrics"]["zero-c"]["fixed_nuisance_observed"]["missing_information_trace_fraction"][
            "median"
        ]
        == 0.5
    )
    assert s["potential_members"] == 148 and s["runtime_sum_s"] == 2
    json.dumps(s, allow_nan=False)


def test_unknown_status_labels_and_nonfinite_rejected():
    plan, receipts = fixture()
    with pytest.raises(ValueError):
        api["summarize"](plan, {"unknown": receipts["synthetic"]}, "hash")
    receipts["synthetic"]["status"] = "pending"
    with pytest.raises(ValueError):
        api["summarize"](plan, receipts, "hash")
    receipts["synthetic"]["status"] = "complete"
    receipts["synthetic"]["elapsed_s"] = float("nan")
    with pytest.raises(ValueError):
        api["summarize"](plan, receipts, "hash")


def test_missing_failure_withholds_distributions_and_checks_identity():
    plan, receipts = fixture()
    assert api["summarize"](plan, {}, "hash")["metrics"] is None
    receipts["synthetic"].update(status="failed", error="MemoryError: budget")
    s = api["summarize"](plan, receipts, "hash")
    assert s["failure_counts"]["resource"] == 1 and s["metrics"] is None
    with pytest.raises(AssertionError):
        api["summarize"](plan, receipts, "wrong")


def test_synthetic_plot_complete_and_empty(tmp_path):
    plan, receipts = fixture()
    for index, rows in enumerate((receipts, {})):
        path = tmp_path / f"{index}.png"
        api["plot"](api["summarize"](plan, rows, "hash"), path)
        assert path.read_bytes().startswith(b"\x89PNG")
