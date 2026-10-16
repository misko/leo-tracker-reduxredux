import importlib.util
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import ds21_model_a_timing_runtime_v2 as previous
import model_a_replacement_path_audit as audit
import numpy as np
import pytest

from leo.analysis.sequential_group_calibration import SequentialShift, fixed_shift_objective
from leo.contracts.regional_position import PositionOrbitBank

_spec = importlib.util.spec_from_file_location(
    "model_a_replacement_public_fixture",
    Path(__file__).with_name("ds21_model_a_timing_runtime_v2_test.py"),
)
_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture)
actual_case = _fixture.actual_case


def models(actual_case, monkeypatch):
    import leo.analysis.hard60_score as score

    monkeypatch.setattr(score, "predict_orbits", audit.predict_orbits)
    monkeypatch.setattr("leo.analysis.hard60_joint_clock.predict_orbits", audit.predict_orbits)
    monkeypatch.setattr(
        "leo.analysis.sequential_group_calibration.predict_orbits", audit.predict_orbits
    )
    _, frozen = actual_case
    case = previous.prepare_case(frozen)
    nodes = case["bank"].nodes_s
    velocity = np.asarray([[2.0, 1.0, -0.5], [-1.0, 2.0, 0.2], [0.5, -1.0, 1.0]])
    origin = np.asarray(
        [[-3900.0, -4400.0, 4400.0], [-3800.0, -4600.0, 4300.0], [-4000.0, -4400.0, 4500.0]]
    )
    bank = PositionOrbitBank(
        case["bank"].numbers,
        nodes,
        origin[:, None, :] + nodes[None, :, None] * velocity[:, None, :],
        np.broadcast_to(velocity[:, None, :], (3, len(nodes), 3)).copy(),
    )
    case = {**case, "bank": bank}
    model = audit.a_models(case)["all"]
    shift = SequentialShift((0, 1), np.array([-24000.0, 38000.0]))
    model = fixed_shift_objective(model.base, shift)
    vector = np.zeros(model.size)
    vector[2:7] = [-80000, 2, -54000, 1.5, -600]
    pred, _, *_ = audit.predict_orbits(
        bank, model.observations, model.prior, vector[:2], np.zeros(3), derivatives=False
    )
    measured = pred[:, 0] + model.correction(vector, np.zeros_like(model.initial_nuisance))
    observed = replace(model.observations, measured_hz=measured)
    case = {**case, "prepared": {**case["prepared"], "all": SimpleNamespace(observations=observed)}}
    return case, fixed_shift_objective(audit.a_models(case)["all"].base, shift), shift


def test_real_objective_band_replay_and_association_alignment(actual_case, monkeypatch):
    _, model, _ = models(actual_case, monkeypatch)
    vector = np.zeros(model.size)
    vector[2:7] = [-80000, 2, -54000, 1.5, -600]
    nuisance = np.zeros_like(model.initial_nuisance)
    value, _, _, terms = model.evaluate_joint(vector, nuisance)
    fit = dict(vector=vector, nuisance=nuisance, objective=value, likelihood_nll=terms.nll)
    counter = dict(objective=0, explicit_predictor=0, band_likelihood=0)
    result = audit.score_state(model, fit, counter)
    assert counter == dict(objective=1, explicit_predictor=1, band_likelihood=2)
    assert result["band_sum_delta"] == pytest.approx(0, abs=1e-8)
    assert sum(b["signal_mass"] for b in result["bands"].values()) == pytest.approx(
        terms.responsibilities.sum()
    )
    assert audit.association_change(result, result)["dominant_candidate_disagreements"] == 0
    assert not any(k.startswith("_") for k in audit.clean(result))
    receipt = Path(actual_case[0]) / "native-band-replay.json"
    audit.immutable(receipt, audit.cached.transport.native_json(audit.clean(result)))
    assert audit.read(receipt)["objective_replay_delta"] == 0
    fit["objective"] += 1
    with pytest.raises(ValueError, match="replay"):
        audit.score_state(model, fit, counter)


def test_replaced_bank_transport_drops_only_omitted_timing_and_retains_correction(
    actual_case, monkeypatch
):
    case, source, shift = models(actual_case, monkeypatch)
    bank = source.bank
    # Genuine public replacement: keep two old satellites and add one declared orbit.
    newbank = PositionOrbitBank(
        np.r_[bank.numbers[:2], 9999],
        bank.nodes_s,
        np.concatenate([bank.position_km[:2], bank.position_km[-1:]], axis=0),
        np.concatenate([bank.velocity_km_s[:2], bank.velocity_km_s[-1:]], axis=0),
    )
    unionbank = audit.transport.union_bank(bank, newbank)
    target = fixed_shift_objective(audit.a_models({**case, "bank": newbank})["all"].base, shift)
    union = fixed_shift_objective(audit.a_models({**case, "bank": unionbank})["all"].base, shift)
    vector = np.zeros(source.size)
    vector[2:8] = [-80000, 2, -54000, 1.5, -600, 3]
    vector[8:] = [2, -1]
    nuisance = np.linspace(-30, 30, len(source.initial_nuisance))
    seed = dict(vector=vector, nuisance=nuisance)
    result = audit.replacement_seed(seed, source, union, target)
    old = dict(zip(bank.numbers, vector[7] + source.basis @ vector[8:], strict=True))
    carried = dict(
        zip(newbank.numbers, result["vector"][7] + target.basis @ result["vector"][8:], strict=True)
    )
    assert carried[9999] == pytest.approx(3, abs=1e-12)
    for n in bank.numbers[:2]:
        assert carried[n] == pytest.approx(old[n], abs=1e-12)
    assert result["correction_closure_hz"] == 0
    assert result["timing_closure_s"] < 1e-12
    target.design = target.design.copy()
    target.design[0, 0] += 1
    with pytest.raises(ValueError, match="design"):
        audit.replacement_seed(seed, source, union, target)


def test_conditional_high_reconstruction_has_single_band_and_no_clock(actual_case, monkeypatch):
    case, _, _ = models(actual_case, monkeypatch)
    base = audit.a_models(case)
    low = dict(
        vector=np.zeros(base["low"].size), nuisance=np.zeros_like(base["low"].initial_nuisance)
    )
    high = audit.SequentialHighObjective(
        base["high"].base,
        audit.freeze_group_calibration(base["low"], low),
        set(base["low"].observations.receiver),
    )
    vector, nuisance = np.zeros(high.size), np.zeros_like(high.initial_nuisance)
    value, _, _, terms = high.evaluate_joint(vector, nuisance)
    fit = dict(vector=vector, nuisance=nuisance, objective=value, likelihood_nll=terms.nll)
    counter = dict(objective=0, explicit_predictor=0, band_likelihood=0)
    result = audit.score_state(high, fit, counter)
    assert set(result["bands"]) == {"high"} and high.clock_count == 0
    assert counter == dict(objective=1, explicit_predictor=1, band_likelihood=1)


def test_orphan_rejected_before_scientific_work(tmp_path, monkeypatch):
    (tmp_path / "protocol.json").write_text("{}")
    (tmp_path / "launch.json").write_text("{}")
    monkeypatch.setattr(audit, "read_control", lambda directory: {})
    with pytest.raises(ValueError, match="no retry"):
        audit.audit(tmp_path)
    assert not (tmp_path / "termination.json").exists()
