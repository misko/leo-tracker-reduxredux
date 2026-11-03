from types import SimpleNamespace

import numpy as np
import pytest

import dense_anchor_fit


def test_dense_anchor_branches_share_seed_and_change_only_anchor_cap(monkeypatch):
    data = SimpleNamespace(
        numbers=np.arange(15),
        group=np.arange(10),
        measured=np.zeros(10),
        times=np.arange(10),
        rf=np.ones(10),
        receiver=np.zeros(10),
        channel=np.zeros(10),
        child_sessions=("scan",),
    )
    assignments = [{"accepted": True}]
    proposal = {"fit": {"rough": {"assignments": assignments}}}
    seed_parameters = np.arange(21, dtype=float)
    seed = {
        "stage": "annealed",
        "fit": {
            "score_leader": {
                "parameters": seed_parameters,
                "satellite_indices": np.arange(12),
            }
        },
    }
    ladder = [
        (np.arange(4), np.ones(4)),
        (np.arange(8), np.ones(8)),
        (np.arange(12), np.ones(12)),
    ]
    sparse = [{"groups": np.arange(2), "track_index": 0}]
    dense = [
        {"groups": np.arange(4), "track_index": 0},
        {"groups": np.arange(4, 7), "track_index": 1},
    ]
    observed = []

    monkeypatch.setattr(
        dense_anchor_fit,
        "candidate_ladder",
        lambda current, sizes: ladder,
    )
    monkeypatch.setattr(
        dense_anchor_fit,
        "anchor_partition",
        lambda data, max_anchors: sparse if max_anchors == 12 else dense,
    )
    monkeypatch.setattr(
        dense_anchor_fit,
        "prepare_track_grouped_likelihood",
        lambda *args, **kwargs: SimpleNamespace(anchor_groups=kwargs["anchors"]),
    )
    monkeypatch.setattr(
        dense_anchor_fit,
        "frozen_row_weights",
        lambda data: np.ones(len(data.times)),
    )
    monkeypatch.setattr(
        dense_anchor_fit,
        "frozen_identity_masses",
        lambda anchors, full_bank, satellites: {
            "anchor_count": len(anchors),
            "bank": np.asarray(satellites).copy(),
        },
    )

    class FakeLikelihood:
        def __init__(self, prepared, masses):
            self.prepared = prepared
            self.masses = masses
            self.last_result = None

    monkeypatch.setattr(dense_anchor_fit, "FixedBankLikelihood", FakeLikelihood)

    def fake_refine(data, initial, satellites, support, likelihood, **options):
        observed.append((initial.copy(), satellites.copy(), likelihood, options.copy()))
        likelihood.last_result = {
            "track_unknown_responsibility": np.zeros(len(dense)),
            "group_count": 10,
        }
        count = len(satellites)
        return {
            "parameters": initial.copy(),
            "success": True,
            "status": "converged",
            "convergence_reason": "synthetic",
            "satellite_indices": satellites.copy(),
            "satellite_count": count,
            "objective": float(100 - count),
            "selection_score": float(100 - count),
            "satellite_weights": np.ones(count) / count,
        }

    monkeypatch.setattr(dense_anchor_fit, "refine_gauss_newton", fake_refine)
    result = dense_anchor_fit.fit_dense_anchors(data, proposal, seed, budget_s=20.0)

    assert [row["satellite_count"] for row in result["trials"]] == [4, 8, 12]
    assert result["coverage_before"]["anchored_group_count"] == 2
    assert result["coverage_after"]["anchored_group_count"] == 7
    assert result["coverage_after"]["anchor_count"] == 2
    assert result["bank_branches_independent"] is True
    assert result["score_leader"]["satellite_count"] == 12
    for initial, satellites, likelihood, options in observed:
        np.testing.assert_array_equal(initial[:6], seed_parameters[:6])
        np.testing.assert_array_equal(initial[6 + satellites], seed_parameters[6 + satellites])
        omitted = np.setdiff1d(np.arange(15), satellites)
        np.testing.assert_array_equal(initial[6 + omitted], 0.0)
        assert likelihood.masses["anchor_count"] == 2
        assert options["budget_s"] == 20.0


def test_dense_anchor_budget_is_bounded():
    with pytest.raises(ValueError, match="budget_s"):
        dense_anchor_fit.fit_dense_anchors(
            SimpleNamespace(numbers=np.arange(1)), {}, {}, budget_s=20.01
        )
