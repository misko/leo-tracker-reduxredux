import numpy as np
import pytest

from tools.evaluate_wrapped_fast_scan import (
    restrict_candidates,
    retain_nested_zero_fit,
    validate_initialization_checkpoint,
    validate_surface_resume,
)


def test_frozen_pool_preserves_identity_phase_and_observation_axes():
    bank = dict(
        norad=np.array([10, 20, 30]),
        position=np.arange(18).reshape(3, 2, 3),
        velocity=np.ones((3, 2, 3)),
        rf_hz=np.array([11e9, 12e9]),
        inverse=[0, 1],
    )
    phases = dict(bank, nodes_s=np.array([0.0, 1.0]))
    seed = dict(active=[2], beta=[1.0, 2.0], satellite_phase_s=[0.1, 0.2, 0.3])
    meta = dict(input_sha256="input", orbit_bank_sha256="orbit")
    pool = dict(input_digest="input", orbit_digest="orbit", norad=[30, 10])
    local, phase, seeds, indices = restrict_candidates(bank, phases, [seed], pool, meta)
    np.testing.assert_array_equal(indices, [0, 2])
    np.testing.assert_array_equal(local["position"], bank["position"][indices])
    assert local["rf_hz"] is bank["rf_hz"]
    assert seeds[0]["active"] == [1]
    assert seeds[0]["satellite_phase_s"] == [0.1, 0.3]
    np.testing.assert_array_equal(phase["norad"], [10, 30])
    with pytest.raises(ValueError, match="different recording"):
        restrict_candidates(bank, phases, [seed], dict(pool, input_digest="forged"), meta)
    with pytest.raises(ValueError, match="distinct candidate"):
        restrict_candidates(bank, phases, [seed], dict(pool, norad=[30, 30]), meta)
    with pytest.raises(ValueError, match="every seeded"):
        restrict_candidates(bank, phases, [seed], dict(pool, norad=[10]), meta)


def test_free_c_retains_the_nested_zero_solution_without_claiming_convergence():
    zero = dict(
        score=20.0,
        beta=[1.0, 2.0],
        labels=["offset", "drift"],
        weights=[0.5, 0.5],
        coefficient_enabled=False,
        converged=True,
        coefficient_hz_ghz=0.0,
    )
    attempted = dict(zero, score=15.0, beta=[1.0, 2.0, 10.0], starts=[{"score": 15.0}])
    retained = retain_nested_zero_fit(attempted, zero)
    assert retained["score"] == 20.0
    assert retained["beta"] == [1.0, 2.0, 0.0]
    assert retained["weights"] == zero["weights"]
    assert retained["coefficient_enabled"]
    assert not retained["converged"]
    assert retained["attempted_free_c_score"] == 15.0
    better = dict(attempted, score=21.0)
    assert retain_nested_zero_fit(better, zero) is better


def test_resume_rejects_changed_science_or_input_and_excess_completed_starts():
    expected = dict(
        config={"scale_hz": 250},
        seeds=[{"phase_s": 0}],
        input_digest="input",
        orbit_digest="orbit",
        source_digests={"kernel": "hash"},
        completed_starts=[],
    )
    previous = dict(expected, completed_starts=[{"score": 2}])
    assert validate_initialization_checkpoint(previous, expected) is previous
    for changed in [
        dict(previous, input_digest="future"),
        dict(previous, source_digests={"kernel": "changed"}),
        dict(previous, config={"scale_hz": 1000}),
    ]:
        with pytest.raises(ValueError, match="protocol changed"):
            validate_initialization_checkpoint(changed, expected)
    with pytest.raises(ValueError, match="exceeds"):
        validate_initialization_checkpoint(dict(previous, completed_starts=[{}, {}]), expected)


def test_surface_resume_allows_wrapper_changes_but_rejects_changed_kernel_or_candidates():
    protocol = dict(
        config={},
        seeds=[],
        random_seed=1,
        input_digest="input",
        orbit_digest="orbit",
        site={},
        phase_receipt={},
        candidate_norad=[20],
        candidate_pool_digest="pool",
        search_plan={"random_points": 12, "prescribed_positions_sha256": "positions"},
        source_digests={
            "src/leo/analysis/wrapped_glrt_likelihood.py": "w",
            "src/leo/analysis/sparse_glrt_likelihood.py": "s",
            "src/leo/analysis/glrt_orbit_phase.py": "p",
            "runner": "old",
        },
    )
    updated = dict(protocol, source_digests=dict(protocol["source_digests"], runner="new"))
    validate_surface_resume(protocol, updated)
    with pytest.raises(ValueError, match="scientific protocol"):
        validate_surface_resume(protocol, dict(updated, candidate_norad=[20, 30]))
    with pytest.raises(ValueError, match="scientific protocol"):
        validate_surface_resume(protocol, dict(updated, search_plan={"random_points": 13}))
    with pytest.raises(ValueError, match="scientific protocol"):
        validate_surface_resume(
            protocol,
            dict(
                updated,
                search_plan={
                    **protocol["search_plan"],
                    "prescribed_positions_sha256": "changed",
                },
            ),
        )
    with pytest.raises(ValueError, match="kernel changed"):
        validate_surface_resume(
            protocol,
            dict(
                updated,
                source_digests={
                    **updated["source_digests"],
                    "src/leo/analysis/glrt_orbit_phase.py": "changed",
                },
            ),
        )

    with pytest.raises(ValueError, match="kernel changed"):
        validate_surface_resume(
            protocol,
            dict(
                updated,
                source_digests={
                    **updated["source_digests"],
                    "src/leo/analysis/wrapped_glrt_likelihood.py": "changed",
                },
            ),
        )


def test_fixed_reception_frame_requires_a_prepared_phase_bank(monkeypatch, capsys):
    from tools.evaluate_wrapped_fast_scan import main

    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate",
            "sweep",
            "--bundle",
            "/unused",
            "--initial",
            "/unused",
            "--output",
            "/unused",
            "--inertial-phase",
        ],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert "requires --phase" in capsys.readouterr().err
