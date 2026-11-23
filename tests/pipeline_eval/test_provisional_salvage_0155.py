from pathlib import Path
import sys
from types import SimpleNamespace

import provisional_salvage_0155 as trial


def test_saved_adapter_runs_original_policy_with_direct_figures(monkeypatch):
    seen = []
    entry = SimpleNamespace(publish_active=lambda args: seen.append(args))
    paths = tuple(Path(name) for name in ("request", "inventory", "output"))

    def candidate(case, request, inventory, output, *, runtime):
        assert case == trial.CASE
        assert (request, inventory, output) == paths
        assert runtime == trial.SETTINGS and trial.original.PINS == trial.PINS
        entry.publish_active(SimpleNamespace())

    monkeypatch.setitem(sys.modules, "unified_short_bootstrap", entry)
    monkeypatch.setattr(trial.original, "candidate_worker", candidate)
    trial.worker(*paths)
    assert vars(seen[0]) == dict(direct_residual_figures=True, direct_orbit_figures=True)


def test_earlier_nominations_and_last_repair_have_separate_reports():
    support = dict(full_curved=12, initial_curved=8, cold_rejected_tracks=["a"],
                   curved_restored=4, salvage=[dict(component="a", selected=dict(points=4))],
                   rechecked_curved=8, second_curved_rejections=["a"], predictive_labels=[])
    result = trial.stages(dict(support=support, pair_passes=False, repair=dict(removed_curved=["b"])))
    assert result["first_gate"]["survivors"] == 8
    assert result["salvage"]["restored"] == 4
    assert result["second_gate"]["rejected"] == ["a"]
    assert result["last_repair"]["removed_curved"] == ["b"]
