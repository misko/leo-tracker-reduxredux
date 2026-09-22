from types import SimpleNamespace

from leo.analysis.blind_regional_association import (
    BlindRegionalMode,
    BlindRegionalResult,
)
from leo.cli.blind_regional import blind_regional_complete, configuration, evaluated_document
from leo.contracts.blind_regional import BlindReferenceV1
from leo.contracts.digests import canonical_digest


def prepared_and_result():
    digest = "sha256:" + "1" * 64
    prepared = SimpleNamespace(
        session_id="scan-test",
        input_manifest_sha256=digest,
        analysis_manifest_sha256=digest,
        source_digest=digest,
        configuration_digest=digest,
        reconstructed_track_count=0,
        reconstructed_observation_count=0,
        eligible_track_count=0,
        eligible_observation_count=0,
        selected_observation_count=0,
        omitted_observation_count=0,
        tracks=(),
        exclusions=(),
        catalogue=SimpleNamespace(
            snapshot_digest=digest,
            catalogue_digest=digest,
            snapshot_collected_utc_ns=100,
            provider="space-track",
            catalog_number=(100, 200),
        ),
    )
    result = BlindRegionalResult(
        state="diagnostic",
        reasons=(),
        blind_positioning=True,
        site_conditioned=False,
        selected_track_count=0,
        coarse_track_count=0,
        omitted_coarse_track_count=0,
        full_observation_count=0,
        search_observation_count=0,
        omitted_search_observation_count=0,
        coarse_point_count=1,
        refined_mode_count=1,
        continuous_refinement_evaluation_count=0,
        map_east_km=(0.0,),
        map_north_km=(0.0,),
        map_training_log_evidence=(1.0,),
        modes=(BlindRegionalMode(38.0, -122.0, 0.0, 0.0, 10.0, 2.0, True, ()),),
    )
    return prepared, result


def test_reference_changes_only_postfit_evaluation():
    prepared, result = prepared_and_result()
    first = evaluated_document(
        prepared,
        result,
        runtime_ms=1,
        reference=BlindReferenceV1(latitude_deg=38, longitude_deg=-122),
    )
    second = evaluated_document(
        prepared,
        result,
        runtime_ms=1,
        reference=BlindReferenceV1(latitude_deg=40, longitude_deg=-100),
    )
    assert first.evaluation.modes[0].horizontal_error_m == 0
    assert second.evaluation.modes[0].horizontal_error_m > 1_000_000
    assert first.model_dump(exclude={"evaluation"}) == second.model_dump(exclude={"evaluation"})


def test_completion_verifies_current_configuration_capture_and_all_pngs(monkeypatch, tmp_path):
    from leo.cli import blind_regional as subject

    reads = []
    document = SimpleNamespace(
        configuration_sha256=canonical_digest(configuration()), input_manifest_sha256="capture-a"
    )
    manifest = SimpleNamespace(
        document=document,
        artifacts=[
            SimpleNamespace(name=name)
            for name in ("blind-association", "blind-position", "blind-position-modes")
        ],
    )
    store = SimpleNamespace(
        status=lambda _: SimpleNamespace(manifest=manifest),
        artifact=lambda sid, name: reads.append(name) or b"verified",
    )
    monkeypatch.setattr(subject, "BlindRegionalStore", lambda _: store)
    assert not blind_regional_complete(tmp_path, "scan", expected_input_manifest_sha256="capture-b")
    assert not reads
    assert blind_regional_complete(tmp_path, "scan", expected_input_manifest_sha256="capture-a")
    assert reads == ["blind-association", "blind-position", "blind-position-modes"]
