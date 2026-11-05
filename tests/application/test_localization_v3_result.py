from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from check_algo07v3_engine import snapshot
from check_algo07v3_publication import evidence_snapshot

from leo.application.localization_v3_result import build_evidence, publish_saved
from leo.contracts.localization_v3 import validate_evidence
from leo.presentation.orbit_plot import OrbitCurve, OrbitLane
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from leo.storage.localization_v3 import LocalizationV3Store
from leo.storage.localization_v3_codec import pack, unpack
from tests.localization_v3_fixture import evidence_fixture


def test_owned_result_publishes_current_figures_and_both_bound_sidecars(tmp_path):
    evidence, pngs = evidence_fixture()
    scientific = LocalizationV3Store(tmp_path)
    public = FastStandardAnalysisStore(tmp_path)
    saved = scientific.save(evidence, pngs)
    assert public.detail("run")["state"] == "pending"
    manifest = publish_saved("run", scientific, public)
    assert manifest["terminal_sha256"] == saved["sha256"]
    assert manifest["implementation_model"] == "algo07v3-exact-v1"
    for name, data in pngs.items():
        assert public.artifact("run", name) == data
    assert public.position_grid("run")["binding"]["terminal_sha256"] == saved["sha256"]
    assert public.position_path("run")["binding"]["terminal_sha256"] == saved["sha256"]
    assert publish_saved("run", scientific, public) == manifest


def test_publication_can_resume_from_saved_result_after_ui_interruption(tmp_path, monkeypatch):
    evidence, pngs = evidence_fixture()
    evidence["render"]["evaluation_reference"] = dict(latitude_deg=37.9, longitude_deg=-122.5)
    scientific = LocalizationV3Store(tmp_path)
    public = FastStandardAnalysisStore(tmp_path)
    saved = scientific.save(evidence, pngs)
    original = public.publish

    def failed(*args, **kwargs):
        raise OSError("UI interruption")

    monkeypatch.setattr(public, "publish", failed)
    with pytest.raises(OSError, match="interruption"):
        publish_saved("run", scientific, public)
    assert scientific.load("run")["sha256"] == saved["sha256"]
    assert public.detail("run")["state"] == "pending"
    monkeypatch.setattr(public, "publish", original)
    publish_saved("run", scientific, public)
    assert public.detail("run")["arms"]["fitted_c"]["evaluation_error_m"] > 0
    assert scientific.load("run")["sha256"] == saved["sha256"]
    publish_saved("run", scientific, public)


@pytest.mark.parametrize("corruption", ["owner", "point", "count", "endpoint", "incomplete"])
def test_scientific_presentation_mismatch_rejected_before_storage(tmp_path, corruption):
    evidence, pngs = evidence_fixture()
    if corruption == "owner":
        evidence["selected"]["owners"]["c0"]["a"] = 12345
    elif corruption == "point":
        evidence["presentation"]["observations"] = [dict(observation_id="b")]
    elif corruption == "count":
        evidence["presentation"]["arms"]["c0"]["associated_points"] = 2
    elif corruption == "endpoint":
        evidence["selected"]["arms"]["c0"]["endpoint_latlon"][0] += 0.01
    else:
        evidence["audit"]["reassociation_complete"]["recovery_complete"] = False
    with pytest.raises(ValueError):
        validate_evidence(evidence)
    with pytest.raises(ValueError):
        LocalizationV3Store(tmp_path).save(evidence, pngs)
    assert not (tmp_path / "localization-v3-v1").exists()


def test_saved_evaluation_site_cannot_silently_disagree_with_figures(tmp_path):
    evidence, pngs = evidence_fixture()
    scientific = LocalizationV3Store(tmp_path)
    public = FastStandardAnalysisStore(tmp_path)
    scientific.save(evidence, pngs)
    publish_saved("run", scientific, public)
    public.set_evaluation_reference("run", 37.0, -122.0)
    before = deepcopy(public.detail("run"))
    with pytest.raises(ValueError, match="reference differs"):
        publish_saved("run", scientific, public)
    assert public.detail("run") == before


def test_projected_and_reloaded_evidence_preserves_existing_full_comparison_scope():
    evidence, pngs = evidence_fixture()
    array = np.array([1.0, 2.0])
    p = SimpleNamespace(
        calculate=lambda x: dict(coefficient=array.copy()),
        state=lambda x: dict(x=x),
        residual=lambda x: array.copy(),
        conditional_frequency=lambda x: array.copy(),
        members=[0],
        labels=[0],
        keep=np.ones(2, bool),
        reference=np.zeros(1),
        events=[],
        event_start=0,
    )
    signed = dict(scan=object(), base=p, x=np.zeros(2), original_protected={3, 2})
    audit = evidence["audit"]
    checkpoints = dict(
        initial=dict(initial_fit=dict(values=array)),
        conservative=dict(conservative_fit=dict(values=array)),
        family=dict(family_fit=dict(values=array)),
        signed=dict(signed_context=signed),
        cavity=dict(nominations=[dict(score=np.float64(2.0))], cavity_fit=dict(values=array)),
        inventory=dict(inventory=dict(values=array)),
        predictive=dict(recovery=dict(values=array)),
        numerical=dict(
            recovery=dict(
                values=array,
                stage_replay=[
                    dict(
                        status="complete",
                        charged_original_seconds=2.0,
                        additional_logical_seconds=3.0,
                        reuse_wall_seconds=4.0,
                        candidate="unchanged",
                    )
                ],
            )
        ),
        gap=dict(
            recovery=dict(stages=[dict(name="gap", seconds=1.0, score=array)]),
            selected_state=dict(owners=evidence["selected"]["owners"]),
        ),
        residual=dict(
            status="additional_recovery_prepared",
            residual_inventory={},
            preflight={},
            residual_context=dict(
                families=[SimpleNamespace(receipt=dict(values=array))], replay_checks={}
            ),
        ),
        residual_screen=dict(values=array),
        addition=dict(values=array),
        incumbent=dict(context=object(), values=array),
        ranking=dict(values=array),
        admission=dict(values=array),
        final=audit["reassociation_complete"],
    )
    inference = dict(
        status="numerics_complete",
        checkpoints=checkpoints,
        context=dict(problems={a: (p, np.zeros(2)) for a in evidence["selected"]["arms"]}),
        **evidence["selected"],
    )
    packet = evidence["presentation"]
    packet["orbit_lanes"] = [
        OrbitLane("RX1", "CH1", (), (OrbitCurve("69333", (0.0, 1.0), (float("nan"), 2.0)),))
    ]
    result = dict(
        status="figures_ready",
        inference=inference,
        preparation=dict(bank=array),
        catalogue=dict(elements={}),
        packet=packet,
        stage_timings=[],
        products=pngs,
    )
    original = snapshot(inference, result)
    projected = build_evidence(
        result,
        identity=evidence["identity"],
        provenance=evidence["provenance"],
        title="fixture",
        renderer_revision="final-error-v7",
    )
    restored, saved_pngs = unpack(pack(projected, pngs))
    assert evidence_snapshot(restored, saved_pngs) == original
    assert restored["audit"]["gap_recovery"]["stages"][0]["seconds"] == 1.0
    assert restored["audit"]["numerical_recovery"]["stage_replay"][0]["reuse_wall_seconds"] == 4.0
    assert "context" not in restored["audit"]["reassociation_handoff"]
