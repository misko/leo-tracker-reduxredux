from types import SimpleNamespace

import numpy as np
import pytest
from check_algo07v3_position import present_owned_result

from leo.presentation import fast_standard_analysis, localization_v3, localization_v3_path


def setup(monkeypatch, *, selected):
    context = dict(
        scan=SimpleNamespace(search_region=object()),
        problems={a: (object(), np.array([1.0, 2.0])) for a in ("c0", "fitted_c")},
    )
    owners = {a: {"native": 2 if selected else 1} for a in context["problems"]}
    expected = {a: dict(proposed_owners=o) for a, o in owners.items()}
    prepared = dict(context=context, arms=expected, owners=owners)
    recovery = dict(
        selected="repair" if selected else None,
        final={a: dict(x=[1.0, 2.0], associated=1) for a in owners},
    )
    final = dict(status="reassociation_evaluated", recovery_complete=True, recovery=recovery)
    retained = [(context, expected)] if selected else []
    observed = []
    path = dict(selected_model="selected", stages=[])
    monkeypatch.setattr(localization_v3_path, "recorded_decision_path", lambda *a, **kw: path)

    def prepare(c, o, e, observations, tracks, **kwargs):
        assert c is context and o == owners and e is expected
        assert kwargs == dict(selected_model="selected", position_path=path)
        observed.append("prepared")
        return dict(position_grid=dict(complete=True, evaluated_points=179, elapsed_seconds=1.0))

    def render(packet, *, title, evaluation_reference):
        assert evaluation_reference is None
        observed.append("rendered")
        return {
            name: b"fixture-png"
            for name in (
                "ch1-4-all",
                "ch5-8-all",
                "ch1-4-unassociated",
                "ch5-8-unassociated",
                "ch1-4-residuals",
                "ch5-8-residuals",
                "track-rms",
                "position",
            )
        }

    monkeypatch.setattr(localization_v3, "prepare_packet", prepare)
    monkeypatch.setattr(fast_standard_analysis, "render", render)
    return prepared, final, retained, observed


def invoke(directory, prepared, final, retained):
    return present_owned_result(
        directory,
        prepared,
        final,
        retained,
        dict(observations=[], tracks=[]),
        cavity={},
        predictive={},
        numerical={},
        gap={},
        additional={},
    )


@pytest.mark.parametrize("selected", [False, True])
def test_fresh_selected_state_supplies_all_artifacts_without_reoptimization(
    monkeypatch, tmp_path, selected
):
    prepared, final, retained, observed = setup(monkeypatch, selected=selected)
    result = invoke(tmp_path / "artifacts", prepared, final, retained)
    assert observed == ["prepared", "rendered"]
    assert len(result["products"]) == len(list((tmp_path / "artifacts").glob("*.png"))) == 8
    assert result["grid_complete"] and result["grid_points"] == 179
    assert (tmp_path / "artifacts/position-path.json").is_file()
    assert (tmp_path / "artifacts/position-grid.json").is_file()


@pytest.mark.parametrize("fault", ["partial", "lost_state", "extra_state", "position", "ownership"])
def test_partial_or_stale_state_cannot_generate_artifacts(monkeypatch, tmp_path, fault):
    prepared, final, retained, observed = setup(monkeypatch, selected=True)
    if fault == "partial":
        final["recovery_complete"] = False
    elif fault == "lost_state":
        retained.clear()
    elif fault == "extra_state":
        retained.append(retained[0])
    elif fault == "position":
        final["recovery"]["final"]["c0"]["x"][0] = 2.0
    else:
        final["recovery"]["final"]["fitted_c"]["associated"] = 2
    with pytest.raises(ValueError):
        invoke(tmp_path / "artifacts", prepared, final, retained)
    assert not observed and not (tmp_path / "artifacts").exists()
