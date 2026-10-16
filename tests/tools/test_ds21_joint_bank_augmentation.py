"""Synthetic ports and checkpoint controls; no DS21 execution or optimization."""

import json
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import ds21_joint_bank_augmentation as driver
import numpy as np
import pytest

from leo.application.scanner_trajectory import project_scanner_candidates
from leo.contracts.regional_position import PositionObservations, PositionOrbitBank, RegionalPrior
from leo.contracts.scanner_tracking import TrackingCandidate, TrackingInput, TrackingProbe
from leo.scanner.persistent_hop import PersistentHopUtcTimingAuthorityV1


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, default=lambda a: a.tolist()))
    return dict(path=str(path), sha256=driver.digest(path))


def forbidden(*args, **kwargs):
    raise AssertionError("Unexpected optimizer/data port")


def synthetic_case():
    rate, origin = 2_500_000, 2**54
    timing = PersistentHopUtcTimingAuthorityV1.from_host_bracket(
        session_id="synthetic",
        session_start_device_sample_counter=origin,
        sample_rate_hz=rate,
        begin_before_realtime_ns=1_788_400_000_000_000_000,
        begin_before_monotonic_ns=1_000_000_000,
        begin_after_realtime_ns=1_788_400_000_002_000_000,
        begin_after_monotonic_ns=1_002_000_000,
        terminal_realtime_ns=1_788_400_040_000_000_000,
        terminal_monotonic_ns=41_000_000_000,
    )
    probes = tuple(
        TrackingProbe(
            i,
            rx,
            0,
            0,
            1 if i % 2 == 0 else 5,
            "lower",
            10.7e9 if i % 2 == 0 else 11.7e9,
            origin + i * rate,
            (2 * i + rx) * rate,
            tuple(
                TrackingCandidate(
                    rank,
                    rate // 25000 + rank * 100,
                    0.25,
                    1200.0 + i * 10 + rank * 30,
                    0.2 - rank * 0.01,
                    0.05,
                    0.15 - rank * 0.01,
                    True,
                )
                for rank in (0, 1)
            ),
        )
        for i in range(4)
        for rx in (0, 1)
    )
    sha = "sha256:" + "a" * 64
    source = TrackingInput(
        "synthetic", "adaptive", rate, "radio", "generation", sha, sha, sha, timing, True, probes
    )
    points = [p for p in project_scanner_candidates(source) if p.candidate_rank == 0]
    obs = PositionObservations(
        tuple(p.source_group_id for p in points),
        [(p.support_center_utc_ns - timing.first_sample_estimate_utc_ns) / 1e9 for p in points],
        [p.measured_cfo_hz for p in points],
        [p.actual_rf_hz for p in points],
        [p.receiver_id for p in points],
        [p.channel for p in points],
        [p.margin for p in points],
    )
    full = PositionOrbitBank(
        [100, 200, 300], [-30.0, 150.0], np.zeros((3, 2, 3)), np.zeros((3, 2, 3))
    )
    case = dict(
        source=source,
        bank=full.select([0, 1]),
        full_bank=full,
        prior=RegionalPrior(),
        prepared=dict(all=SimpleNamespace(observations=obs, evidence_sha256="prepared")),
        held=dict(all=obs),
        split=SimpleNamespace(training=source, held=source),
        member=dict(input=dict(path="synthetic.json", sha256=sha)),
        protocol_sha256="discovery",
        proposal_binding=dict(protocol_sha256="proposals", terminal_sha256="proposal-terminal"),
        proposal_seeds=dict(all=[dict(id=f"p{i}") for i in range(6)]),
    )
    selection = dict(
        state="selected",
        original_numbers=[100, 200],
        original_full_indices=[0, 1],
        added_numbers=[300],
        added_full_indices=[2],
        augmented_numbers=[100, 200, 300],
        augmented_full_indices=[0, 1, 2],
        source_binding=dict(bank_npz_sha256="bank"),
    )
    return case, selection


def orbit_stub(bank, obs, prior, point, shifts, *, derivatives=True):
    n, k = len(obs.window_ids), len(bank.numbers)
    spatial = np.empty((n, k, 2))
    spatial[..., 0] = 0.5 + obs.times_s[:, None] * 0.01 + bank.numbers[None, :] / 1000
    spatial[..., 1] = 0.2 + obs.receiver[:, None] * 0.1
    timing = np.broadcast_to(2 + bank.numbers[None, :] / 1000, (n, k)).copy()
    prediction = (
        1200
        + obs.times_s[:, None] * 10
        + bank.numbers[None, :] / 10
        + spatial @ np.asarray(point)
        + timing * shifts
    )
    return prediction, np.ones((n, k), bool), spatial, timing


@pytest.fixture
def models(monkeypatch):
    import ds21_joint_candidates as candidates

    import leo.analysis.joint_association_score as objective

    monkeypatch.setattr(objective, "predict_orbits", orbit_stub)
    monkeypatch.setattr(candidates, "predict_orbits", orbit_stub)
    case, selection = synthetic_case()
    obs = case["prepared"]["all"].observations
    old = driver.bank_objective(case, case["source"], obs)[0]
    expanded_case = driver.selected_case(case, selection, "augmented")
    new = driver.bank_objective(expanded_case, case["source"], obs)[0]
    seed = dict(
        vector=[1.0, -2.0, 4.0, 0.5, -3.0, -0.2, 10.0, 0.3, 0.4],
        nuisance=[2.0, -1.0],
        projection=dict(inherited="original"),
    )
    return case, selection, old, new, seed


def test_transport_keeps_original_seed_and_embeds_timing_by_catalogue(models):
    case, selection, old, new, seed = models
    before = deepcopy(seed)
    assert driver.transport_seed(seed, old, old) == seed
    carried = driver.transport_seed(seed, old, new)
    np.testing.assert_array_equal(carried["vector"][:8], seed["vector"][:8])
    assert carried["nuisance"] == seed["nuisance"] and seed == before
    old_shifts = seed["vector"][7] + old.basis @ seed["vector"][8:]
    new_shifts = carried["vector"][7] + new.basis @ carried["vector"][8:]
    np.testing.assert_allclose(new_shifts, [*old_shifts, seed["vector"][7]], atol=1e-14)
    assert carried["timing_transport"]["relative_penalty_delta"] == pytest.approx(0, abs=1e-14)
    assert old.score == new.score and old.group_count == new.group_count == 2
    # Signal/clutter mass fixed, satellite mass divided uniformly by each K.
    assert old.base.initial[0] == new.base.initial[0]
    assert old.base.initial[1:].sum() == pytest.approx(new.base.initial[1:].sum())
    assert old.base.initial[1] / new.base.initial[1] == pytest.approx(3 / 2)
    assert driver.selected_case(case, selection, "original")["bank"].numbers.tolist() == [100, 200]


def test_transport_is_identity_based_under_reordering_and_rejects_frame_change(models):
    case, _, old, _, seed = models
    reordered = {**case, "bank": case["full_bank"].select([2, 1, 0])}
    target = driver.bank_objective(reordered, case["source"], case["held"]["all"])[0]
    carried = driver.transport_seed(seed, old, target)
    shifts = carried["vector"][7] + target.basis @ carried["vector"][8:]
    old_shifts = seed["vector"][7] + old.basis @ seed["vector"][8:]
    np.testing.assert_allclose(shifts, [seed["vector"][7], old_shifts[1], old_shifts[0]])
    target.frame = replace(target.frame, high_fractions=(0.25, 0.25))
    with pytest.raises(ValueError, match="frame"):
        driver.transport_seed(seed, old, target)


def test_selection_cap_mapping_empty_pool_and_no_substitution(models):
    case, selection, _, _, _ = models
    metadata = dict(
        proposals=dict(candidate_numbers=[100, 200], candidate_full_indices=[0, 1]),
        discovery=dict(bank_npz=dict(sha256="bank")),
    )
    assert driver.validate_selection(selection, metadata)
    for change in (
        dict(added_numbers=[100]),
        dict(added_numbers=[]),
        dict(added_full_indices=[1]),
        dict(augmented_numbers=[300, 100, 200]),
    ):
        with pytest.raises(ValueError, match="expansion"):
            driver.validate_selection({**selection, **change}, metadata)
    assert not driver.validate_selection(
        {**selection, "state": "unavailable", "added_numbers": []}, metadata
    )
    with pytest.raises(ValueError, match="catalogue mapping"):
        driver.selected_case(case, {**selection, "augmented_full_indices": [0, 2, 1]}, "augmented")


def test_baseline_replays_all_actual_arm_starts_and_winners(tmp_path, models, monkeypatch):
    case, _, old, _, seed = models
    for i in range(6):
        write(tmp_path / "seeds" / f"all-{i}.json", dict(seed=seed))
    winners = {}
    for arm in driver.ARMS:
        vector = np.asarray(seed["vector"]).copy()
        if arm == "zero-c":
            vector[6] = 0
        value, _, _, terms = old.evaluate_joint(vector, np.asarray(seed["nuisance"]))
        winners[arm] = dict(
            state="selected",
            fit=dict(
                vector=vector.tolist(),
                nuisance=seed["nuisance"],
                objective=value,
                likelihood_nll=terms.nll,
            ),
        )
    monkeypatch.setattr(driver, "validate_baseline_sources", lambda case: {"core": "frozen"})
    metadata = dict(
        winners=winners, proposals=dict(candidate_numbers=[100, 200], candidate_full_indices=[0, 1])
    )
    rows = driver.baseline_replay(case, metadata, tmp_path)
    assert len(rows) == 14 and all(row["passed"] for row in rows)
    assert {row["state"] for row in rows} == {
        *(f"seed-{i}-{arm}" for i in range(6) for arm in driver.ARMS),
        *(f"winner-{arm}" for arm in driver.ARMS),
    }
    winners["fitted-c"]["fit"]["likelihood_nll"] += 1.0
    rows = driver.baseline_replay(case, metadata, tmp_path)
    assert not next(row["passed"] for row in rows if row["state"] == "winner-fitted-c")


@pytest.mark.parametrize("variant", driver.VARIANTS)
def test_own_held_scorer_uses_fixed_state_same_native_rows(models, variant):
    case, selection, _, _, seed = models
    original = driver.bank_objective(case, case["source"], case["held"]["all"])[0]
    chosen = driver.selected_case(case, selection, variant)
    model = driver.bank_objective(chosen, case["source"], case["held"]["all"])[0]
    fit = driver.transport_seed(seed, original, model)
    before = deepcopy(fit)
    result = driver.candidate_held_prediction(
        chosen, case["source"], case["held"]["all"], model, fit, variant="all-candidates"
    )
    assert result["window_ids"] == case["held"]["all"].window_ids
    assert result["nll_per_window"] == result["nll"] / len(result["window_ids"])
    np.testing.assert_array_equal(fit["vector"], before["vector"])
    assert fit["nuisance"] == before["nuisance"]
    assert result["held_fitting"] == "none; training correction, position and timing frozen"


def test_checkpoint_failed_outcome_is_preserved_but_orphan_launch_cannot_retry(tmp_path):
    ids = [f"p{i}" for i in range(6)]
    row = dict(protocol_sha256="frozen", proposal_id="p0")
    path = tmp_path / "attempts/all-0-zero-c.json"
    write(path, dict(**row, fit=dict(converged=False, reason="no feasible evaluation")))
    write(tmp_path / "launches/all-0-zero-c.json", row)
    before = path.read_bytes()
    driver.validate_attempts(tmp_path, "frozen", ids)
    assert path.read_bytes() == before
    write(tmp_path / "launches/all-0-fitted-c.json", row)
    with pytest.raises(ValueError, match="Orphan optimizer launch"):
        driver.validate_attempts(tmp_path, "frozen", ids)


def test_checkpoint_cannot_promote_contradictory_stationarity_flag(tmp_path):
    row = dict(protocol_sha256="frozen", proposal_id="p0")
    write(tmp_path / "launches/all-0-fitted-c.json", row)
    write(
        tmp_path / "attempts/all-0-fitted-c.json",
        dict(**row, fit=dict(converged=True, objective=1.0, stationarity=0.1)),
    )
    with pytest.raises(ValueError, match="stationary objective"):
        driver.validate_attempts(tmp_path, "frozen", [f"p{i}" for i in range(6)])


def test_expanded_model_analytic_gradient_matches_native_objective(models):
    _, _, old, target, seed = models
    lifted = driver.transport_seed(seed, old, target)
    vector, nuisance = np.asarray(lifted["vector"]), np.asarray(lifted["nuisance"])
    _, gradient, extra, _ = target.evaluate_joint(vector, nuisance)
    numeric = []
    for i in range(len(vector)):
        delta = np.zeros_like(vector)
        delta[i] = 1e-4
        numeric.append(
            (
                target.evaluate_joint(vector + delta, nuisance)[0]
                - target.evaluate_joint(vector - delta, nuisance)[0]
            )
            / 2e-4
        )
    np.testing.assert_allclose(gradient, numeric, atol=2e-8, rtol=2e-5)
    for i in range(len(nuisance)):
        delta = np.zeros_like(nuisance)
        delta[i] = 1e-4
        derivative = (
            target.evaluate_joint(vector, nuisance + delta)[0]
            - target.evaluate_joint(vector, nuisance - delta)[0]
        ) / 2e-4
        assert extra[i] == pytest.approx(derivative, abs=2e-8, rel=2e-5)


@pytest.mark.parametrize("name", ["all-6-zero-c.json", "half-0-fitted-c.json"])
def test_checkpoint_rejects_extra_start_or_view(tmp_path, name):
    write(tmp_path / "launches" / name, {})
    with pytest.raises(ValueError, match="twelve fixed attempts"):
        driver.validate_attempts(tmp_path, "frozen", [f"p{i}" for i in range(6)])


def run_fixture(tmp_path, monkeypatch, models):
    import ds21_joint_proposals as common
    import ds21_shared_proposals as shared

    case, selection, _, _, seed = models
    protocol = tmp_path / "freeze.json"
    write(protocol, driver.FROZEN_FIELDS)
    parent = tmp_path / "original-seeds"
    lifts = [dict(receiver=0, integer=-1), dict(receiver=1, integer=2)]
    for i in range(6):
        write(parent / "seeds" / f"all-{i}.json", dict(seed=seed, receiver_branch_lifts=lifts))
    metadata_case = dict(
        source_input=case["member"]["input"],
        parent=dict(prepared_all_sha256="prepared"),
        discovery=dict(protocol=dict(sha256="discovery")),
        proposals=dict(
            protocol=dict(sha256="proposals"), terminal=dict(sha256="proposal-terminal")
        ),
    )
    monkeypatch.setattr(driver, "OUTPUT", tmp_path)
    monkeypatch.setattr(common, "OUTPUT", tmp_path)
    monkeypatch.setattr(shared, "load_case_with_proposals", lambda label: case)
    monkeypatch.setattr(
        driver,
        "read_freeze",
        lambda path, label, variant: (
            dict(loaded_source_sha256={}, metadata={}, physical_seed_protocol={}, oracle={}),
            {},
            metadata_case,
            {},
            selection,
            parent,
            True,
        ),
    )
    monkeypatch.setattr(driver, "validate_source_freeze", lambda frozen: {})
    return common, protocol


@pytest.mark.parametrize("variant", driver.VARIANTS)
def test_real_common_runner_matched_calls_failures_cache_and_no_retry(
    tmp_path, monkeypatch, models, variant
):
    common, protocol = run_fixture(tmp_path, monkeypatch, models)
    calls = []

    def synthetic_fit(model, vector, nuisance, **kwargs):
        calls.append(kwargs)
        assert kwargs["seconds"] == 20 and kwargs["iterations"] == 600
        assert kwargs["local_radius_km"] == 25
        # No numerical optimizer is called; failure outcomes are authoritative.
        if len(calls) == 1:
            raise TimeoutError("synthetic no-vector failure")
        if len(calls) == 12:
            return dict(
                converged=True,
                stationarity=0.1,
                objective=100.0,
                reason="synthetic contradictory convergence flag",
            )
        vector = np.asarray(vector).copy()
        if kwargs["arm"] == "zero-c":
            vector[6] = 0
        value, _, _, terms = model.evaluate_joint(vector, nuisance)
        return dict(
            converged=True,
            stationarity=0.0,
            objective=value,
            vector=vector.tolist(),
            nuisance=nuisance.tolist(),
            likelihood_nll=terms.nll,
        )

    monkeypatch.setattr(common, "fit_group_calibration", synthetic_fit)
    result = driver.run("DS21-005", variant, protocol)
    assert len(calls) == 12 and {c["arm"] for c in calls} == set(driver.ARMS)
    assert result["results"]["all"]["selected"]["fitted-c"]["start"] == 1
    assert not result["results"]["all"]["attempts"]["fitted-c"][0]["fit"]["converged"]
    rejected = result["results"]["all"]["attempts"]["zero-c"][-1]["fit"]
    assert rejected["reported_converged"] and not rejected["converged"]
    monkeypatch.setattr(common, "fit_group_calibration", forbidden)
    cached = driver.run("DS21-005", variant, protocol)
    assert cached == json.loads(json.dumps(result, default=lambda a: a.tolist()))


def test_external_failure_receipts_block_repeat_of_unrecorded_call(tmp_path, monkeypatch, models):
    common, protocol = run_fixture(tmp_path, monkeypatch, models)

    def interrupted(*args, **kwargs):
        raise RuntimeError("synthetic interrupted invocation")

    monkeypatch.setattr(common, "fit_group_calibration", interrupted)
    with pytest.raises(RuntimeError, match="interrupted invocation"):
        driver.run("DS21-005", "original", protocol)
    directory = tmp_path / "local/joint-common-bank-original-v1/DS21-005"
    termination = json.loads((directory / "terminations/all-0-fitted-c.json").read_text())
    assert termination["error_type"] == "RuntimeError" and not termination["optimizer_returned"]
    monkeypatch.setattr(common, "fit_group_calibration", forbidden)
    with pytest.raises(ValueError, match="Orphan optimizer launch"):
        driver.run("DS21-005", "original", protocol)


def test_historical_source_bridge_includes_candidate_constructor_tools(tmp_path, monkeypatch):
    paths = {}
    old_sources, mapping = {}, {}
    for i, name in enumerate(
        (
            "src/leo/analysis/joint_association_candidates.py",
            "tools/joint_association_candidates_native.py",
        )
    ):
        path = tmp_path / "live" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# original computational bytes {i}\n")
        paths[name] = path
        old_name = "/historical/" + name
        old_sources[old_name] = driver.digest(path)
        mapping[old_name] = f"{i}.py"
        archive = tmp_path / "parent/source-snapshot" / mapping[old_name]
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(path.read_bytes())
    protocol = write(
        tmp_path / "parent/protocol.json", dict(sources=old_sources, source_snapshot_paths=mapping)
    )
    monkeypatch.setattr(driver, "candidate_sources", lambda: paths)
    metadata = dict(parent=dict(protocol=protocol))
    assert set(driver.validate_baseline_sources(metadata)) == set(paths)
    paths["tools/joint_association_candidates_native.py"].write_text("# changed candidate input\n")
    with pytest.raises(ValueError, match="computational source differs"):
        driver.validate_baseline_sources(metadata)


def test_current_source_and_loaded_closure_seals(tmp_path, monkeypatch):
    path = tmp_path / "scientific.py"
    path.write_text("# frozen code\n")
    sha = driver.digest(path)
    monkeypatch.setattr(driver, "scientific_sources", lambda: {"code": path})
    monkeypatch.setattr(driver, "loaded_source_hashes", lambda: {str(path): sha})
    frozen = dict(source_sha256={"code": sha}, loaded_source_sha256={str(path): sha})
    driver.validate_source_freeze(frozen)
    path.write_text("# changed code\n")
    with pytest.raises(ValueError, match="scientific source changed"):
        driver.validate_source_freeze(frozen)
    path.write_text("# frozen code\n")
    monkeypatch.setattr(driver, "loaded_source_hashes", lambda: {"late-import": "new"})
    with pytest.raises(ValueError, match="loaded source closure"):
        driver.validate_source_freeze(frozen)


@pytest.mark.parametrize(
    "mutation",
    [
        dict(iterations=601),
        dict(starts=7),
        dict(maximum_new_fit_calls=49),
        dict(local_radius_km=30),
    ],
)
def test_freeze_rejects_scope_change_before_any_data_port(tmp_path, monkeypatch, mutation):
    protocol = tmp_path / "freeze.json"
    write(protocol, {**driver.FROZEN_FIELDS, **mutation})
    monkeypatch.setattr(driver, "validate_inventory", forbidden)
    with pytest.raises(ValueError, match="frozen bank-control scope"):
        driver.read_freeze(protocol, "DS21-005", "augmented")


def test_unavailable_intervention_never_loads_data_or_calls_optimizer(tmp_path, monkeypatch):
    import ds21_shared_proposals as shared

    protocol = tmp_path / "freeze.json"
    write(protocol, {})
    monkeypatch.setattr(driver, "OUTPUT", tmp_path)
    monkeypatch.setattr(shared, "load_case_with_proposals", forbidden)
    monkeypatch.setattr(driver, "run_proposals", forbidden)
    monkeypatch.setattr(
        driver,
        "read_freeze",
        lambda *args: ({}, {}, {}, {}, dict(state="unavailable", added_numbers=[]), None, False),
    )
    for variant in driver.VARIANTS:
        result = driver.run("DS21-005", variant, protocol)
        assert result["state"] == "unavailable" and result["optimizer_calls"] == 0
