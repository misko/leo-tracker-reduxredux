from types import SimpleNamespace

import numpy as np

from leo.analysis.localization_v3 import acceptance, discovery, position, scan
from tools.pipeline_eval.variants import algo08_sampled_initial as proposal, v5_core


def track(key, times):
    times = np.asarray(times, float)
    return dict(key=key, times=times, values=times**2, channel=1,
                observation_ids=[f"{key}:{k}" for k in range(len(times))])


def fixture():
    tracks = [track("long", np.arange(65)), track("linear", [0, 10]), track("short", [3, 4, 5])]
    times = np.unique(np.concatenate([t["times"] for t in tracks]))
    return SimpleNamespace(tracks=tracks, curved=[0, 2], times=times, sky=object(),
                           rx_basis=[t["times"][:, None] for t in tracks], radio_sigma_hz=60,
                           norads=np.array([101, 202]))


def test_sample_spreads_over_wall_time_and_preserves_short_tracks():
    times = np.r_[np.linspace(0, 1, 100), 50, 100]
    indices = proposal.spread(times)
    assert len(indices) == proposal.TRACK_SAMPLES
    assert indices[0] == 0 and indices[-1] == len(times) - 1
    assert 100 in indices  # A sparse interior time keeps coverage despite the dense leading cluster.
    assert np.all(np.diff(indices) > 0)
    np.testing.assert_array_equal(proposal.spread(times), indices)
    np.testing.assert_array_equal(proposal.spread(times[:3]), np.arange(3))


def test_sample_lockstep_and_full_curved_eligibility(monkeypatch):
    full = fixture()
    monkeypatch.setattr(scan, "prepare_phase_geometry", lambda bank, times: (bank, times))
    reduced = proposal.sampled_scan(full)
    assert reduced is not full
    assert reduced.norads is full.norads and reduced.sky is full.sky
    assert reduced.causal_uncertainty_modes is full.causal_uncertainty_modes
    assert [t["key"] for t in reduced.tracks] == ["long", "short"]
    assert reduced.curved == [0, 1]
    for k, i in enumerate(full.curved):
        t, low = full.tracks[i], reduced.tracks[k]
        selected = proposal.spread(t["times"])
        assert low["observation_ids"] == [t["observation_ids"][r] for r in selected]
        np.testing.assert_array_equal(low["values"], t["values"][selected])
        np.testing.assert_array_equal(reduced.rx_basis[k], full.rx_basis[i][selected])
        np.testing.assert_array_equal(reduced.times[reduced.index[k]], low["times"])
    assert full.curved == [0, 2]
    assert len(full.tracks[0]["times"]) == 65


def test_full_data_reorders_branches_and_owns_all_gate_inputs(monkeypatch):
    full = fixture()
    coarse = SimpleNamespace(curved=[0, 1], tracks=[track("long", np.arange(16)), full.tracks[2]],
                             times=np.arange(16), radio_sigma_hz=full.radio_sigma_hz)
    monkeypatch.setattr(proposal, "sampled_scan", lambda _: coarse)
    nodes = [dict(aliases=[0, 0], seed=dict(rows=[dict(component=t, candidate_index=j, points=4)
                 for t in ("long", "short")])) for j in range(2)]
    monkeypatch.setattr(v5_core, "ranked_initial_nodes", lambda received: nodes if received is coarse else [])
    early_rounds, full_rounds = [], []

    def sampled(received, sigma, node, arm, *, rounds):
        assert received is coarse and arm == "c0"
        early_rounds.append(rounds)
        return None, dict(parameters=[1, 2], score=node is nodes[1]), [dict(posterior_phase_s=[2.0])]

    def full_model(received, node, sigma, fitted, *, reference):
        assert received is full and not fitted
        assert [r["points"] for r in node["seed"]["rows"]] == [65, 3]
        assert "cost" not in node["seed"]["rows"][0]
        j = node["seed"]["rows"][0]["candidate_index"]
        full_rounds.append((j, float(reference[0])))
        return SimpleNamespace(rows=node["seed"]["rows"], alias=node["aliases"], labels=[j],
                               state=lambda _: dict(phases=np.array([4.0, 5.0])))

    def full_fit(model, point):
        return dict(parameters=point, score=10 - model.labels[0], active_points=68)

    def gate(model, record, arm, point):
        assert model.labels == [1] and arm == "c0"
        assert record["fits"][0]["active_points"] == 68
        return dict(accepted_points=68)

    monkeypatch.setattr(position, "refreshed", sampled)
    monkeypatch.setattr(position, "NormalPosition", full_model)
    monkeypatch.setattr(position, "fit", full_fit)
    monkeypatch.setattr(acceptance, "actual_metrics", gate)
    detail = {}
    selected, branches = proposal.select(full, detail)
    assert branches == 2 and detail["selected_rank"] == 1
    assert early_rounds == [2, 2]
    assert full_rounds == [(0, 2.0), (0, 4.0), (0, 4.0), (1, 2.0), (1, 5.0), (1, 5.0)]
    assert selected["choices"][0]["node"]["seed"]["rows"][0]["candidate_norad"] == 202
    assert discovery.signature(selected["choices"][0]["node"]) == (
        ("long", 1, 202, 0), ("short", 1, 202, 0)
    )
