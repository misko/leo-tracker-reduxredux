import importlib.util
from pathlib import Path
from types import SimpleNamespace

import model_a_production_q_budget_replay as replay
import numpy as np
import pytest

spec = importlib.util.spec_from_file_location(
    "production_q_replay_fixture", Path(__file__).parents[1] / "analysis/test_shared_scan_model.py"
)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
actual_case, family = fixture.actual_case, fixture.family


def test_saved_sources_reconstruct_complete_states_qzero_exact_functions_and_own_disks(family):
    raw, v, n, shift = family
    prepared = dict(all=SimpleNamespace(observations=raw.observations))
    options = dict(fixed_position=False, local_radius_km=25, local_center=[0.0, 0.0])
    saved = {
        "A-5-low": dict(result=dict(audit=dict(accepted=True))),
        "A-5-high": dict(
            result=dict(
                audit=dict(accepted=True),
                fit=dict(group_receivers=shift.receivers, group_offsets_hz=shift.offsets_hz),
            )
        ),
        "A-5-final": dict(
            result=dict(audit=dict(accepted=True), fit=dict(vector=v, nuisance=n), options=options)
        ),
        "B-2": dict(
            result=dict(
                audit=dict(accepted=True),
                fit=dict(vector=v, nuisance=np.r_[n, shift.offsets_hz]),
                options=dict(options, local_center=[25.0, 0.0]),
            )
        ),
    }
    rows = replay.reconstruct_sources(
        prepared, raw.bank, raw.prior, raw.base.nodes, dict(A="A-5", B_index=2), saved.__getitem__
    )
    assert [r["name"] for r in rows] == ["A-5", "B-all"]
    a, b = rows
    np.testing.assert_array_equal(a["vector"], v)
    np.testing.assert_array_equal(a["nuisance"][: len(n)], n)
    assert np.all(a["nuisance"][len(n) :] == 0)
    np.testing.assert_array_equal(a["model"].original.baseline, raw.baseline)
    assert a["options"]["local_center"] == [0.0, 0.0]
    assert b["options"]["local_center"] == [25.0, 0.0]
    assert b["donor_correction_error_hz"] < 1e-8
    assert len(b["nuisance"]) == len(b["model"].initial_nuisance)
    saved["A-5-high"]["result"]["audit"]["accepted"] = False
    with pytest.raises(ValueError, match="must all be strict"):
        replay.reconstruct_sources(
            prepared,
            raw.bank,
            raw.prior,
            raw.base.nodes,
            dict(A="A-5", B_index=2),
            saved.__getitem__,
        )


def test_parent_authority_checks_actual_stage_inventory_and_public_input(tmp_path):
    public = tmp_path / "input.json"
    replay.persist(public, dict(source="synthetic"))
    parent = tmp_path / "r1"
    replay.persist(
        parent / "launch.json",
        dict(
            model_version="shared-scan-q-v1",
            input_path=str(public),
            input_sha256=replay.binding(public)["sha256"],
        ),
    )
    replay.persist(
        parent / "stages/source-selection.json",
        dict(A="A-0", B_index=2, A_prescreen=[dict(source="A-0", J=10), dict(source="A-1", J=20)]),
    )
    replay.persist(
        parent / "stages/B-2.json",
        dict(result=dict(audit=dict(accepted=True), fit=dict(objective=3.0))),
    )
    pins = [replay.binding(p) for p in sorted((parent / "stages").glob("*.json"))]
    replay.persist(
        parent / "terminal.json",
        dict(
            model_version="shared-scan-q-v1",
            state="unavailable",
            input_sha256=replay.binding(public)["sha256"],
            unfinished_stages=[],
            reference_usage="none",
            stage_receipts=pins,
        ),
    )
    assert replay.verify_parent(parent)[2]["B_index"] == 2
    replay.persist(parent / "stages/extra.json", dict(orphan=True))
    with pytest.raises(ValueError, match="inventory changed"):
        replay.verify_parent(parent)
