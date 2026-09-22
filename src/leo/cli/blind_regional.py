"""Publish blind catalogue association and position alongside assisted tracking."""

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

from leo.contracts.blind_regional import (
    BlindAccountingV1,
    BlindCandidateV1,
    BlindEvaluationV1,
    BlindExclusionV1,
    BlindModeEvaluationV1,
    BlindPositionModeV1,
    BlindReferenceV1,
    BlindRegionalDocumentV1,
    BlindRegionV1,
    BlindSnapshotRefV1,
    BlindTrackAssociationV1,
)
from leo.contracts.digests import canonical_digest
from leo.storage.blind_regional import BlindRegionalStore


def configuration():
    # Keep numerical imports out of queue inventory checks until needed.
    from leo.analysis.blind_regional_association import BlindRegionalConfig
    from leo.operations.blind_tracking_inputs import BlindInputLimits, BlindRegion

    return json.loads(
        json.dumps(
            {
                "analysis_id": "scanner-blind-regional-v1",
                "inputs": asdict(BlindInputLimits()),
                "region": asdict(BlindRegion()),
                "numerics": asdict(BlindRegionalConfig()),
                "candidate_policy": "full-causal-catalogue-at-every-trial-location",
                "known_position_used_for_inference": False,
                "reference_policy": "evaluation-after-fit-only",
            }
        )
    )


def blind_regional_complete(
    root: Path, session_id: str, *, expected_input_manifest_sha256: str | None = None
) -> bool:
    store = BlindRegionalStore(root)
    status = store.status(session_id)
    if status.manifest is None:
        return False
    document = status.manifest.document
    if document.configuration_sha256 != canonical_digest(configuration()):
        return False
    if (
        expected_input_manifest_sha256 is not None
        and document.input_manifest_sha256 != expected_input_manifest_sha256
    ):
        return False
    return all(
        store.artifact(session_id, item.name) is not None for item in status.manifest.artifacts
    )


def _region():
    config = configuration()
    return BlindRegionV1(
        **config["region"],
        grid_policy="uniform-azimuthal-equidistant-training-search-v1",
        refinement_policy="bounded-full-catalogue-training-refinement-v1",
    )


def evaluated_document(prepared, result, *, runtime_ms: int, reference=None):
    """The reference enters only after the blind numerical result exists."""
    from leo.cli.scan_position_methods import reference_error_m

    modes = tuple(
        BlindPositionModeV1(
            rank=index,
            state="diagnostic",
            latitude_deg=mode.latitude_deg,
            longitude_deg=mode.longitude_deg,
            training_score=mode.training_log_evidence,
            heldout_score=mode.heldout_log_evidence,
            reasons=() if mode.refined else ("coarse-alternative-not-refined",),
        )
        for index, mode in enumerate(result.modes, start=1)
    )
    source_by_id = {track.track_id: track for track in prepared.tracks}
    tracks = []
    if result.modes:
        for association in result.modes[0].track_associations:
            source = source_by_id[association.track_id]
            candidates = tuple(
                BlindCandidateV1(
                    catalog_number=candidate.catalog_number,
                    training_score=candidate.training_log_score,
                    heldout_score=candidate.heldout_log_score,
                    soft_weight=candidate.weight,
                )
                for candidate in association.top_candidates
            )
            prediction = association.prediction_hz
            has_prediction = len(prediction) == len(source.support_center_utc_ns)
            tracks.append(
                BlindTrackAssociationV1(
                    track_id=association.track_id,
                    state=association.association_state,
                    catalogue_size=len(prepared.catalogue.catalog_number),
                    candidates=candidates,
                    unassigned_weight=association.null_weight,
                    observation_utc_ns=tuple(map(int, source.support_center_utc_ns))
                    if has_prediction
                    else (),
                    observed_hz=association.measured_hz if has_prediction else (),
                    predicted_hz=prediction if has_prediction else (),
                    residual_hz=tuple(
                        y - p for y, p in zip(association.measured_hz, prediction, strict=True)
                    )
                    if has_prediction
                    else (),
                    diagnostics=json.loads(json.dumps(asdict(association))),
                )
            )
    exclusions = tuple(
        BlindExclusionV1(
            scope_id=f"{item.scope}:{item.identity}", reason=item.reason, detail=item.detail
        )
        for item in prepared.exclusions
    )
    catalogue = prepared.catalogue
    diagnostics = json.loads(json.dumps(asdict(result)))
    diagnostics.update(
        {
            "input_source_digest": prepared.source_digest,
            "input_configuration_digest": prepared.configuration_digest,
            "catalogue_universe_digest": prepared.catalogue.catalogue_digest,
            "track_support": [
                {
                    "track_id": track.track_id,
                    "source_digest": track.source_digest,
                    "observation_id": list(track.observation_id),
                }
                for track in prepared.tracks
            ],
            "reconstructed_track_count": prepared.reconstructed_track_count,
            "eligible_track_count": prepared.eligible_track_count,
            "eligible_observation_count_before_limits": prepared.eligible_observation_count,
            "omitted_observation_count": prepared.omitted_observation_count,
            "configuration": configuration(),
        }
    )
    return BlindRegionalDocumentV1(
        session_id=prepared.session_id,
        input_manifest_sha256=prepared.input_manifest_sha256,
        analysis_manifest_sha256=prepared.analysis_manifest_sha256,
        configuration_sha256=canonical_digest(configuration()),
        region=_region(),
        causal_snapshots=(
            BlindSnapshotRefV1(
                digest=catalogue.snapshot_digest,
                collected_utc_ns=catalogue.snapshot_collected_utc_ns,
                provider=catalogue.provider,
                object_count=len(catalogue.catalog_number),
            ),
        ),
        accounting=BlindAccountingV1(
            saved_observation_count=prepared.reconstructed_observation_count,
            eligible_observation_count=prepared.selected_observation_count,
            track_count=len(tracks),
            associated_track_count=sum(track.state == "associated" for track in tracks),
            excluded_count=len(exclusions),
            recorded_exclusion_count=min(8192, len(exclusions)),
            propagation_evaluation_count=len(catalogue.catalog_number)
            * prepared.selected_observation_count,
            objective_evaluation_count=(
                result.coarse_point_count
                + result.refined_mode_count
                * len(configuration()["numerics"]["refinement_half_width_km"])
                * configuration()["numerics"]["refinement_grid_side"] ** 2
                + result.continuous_refinement_evaluation_count
                + len(result.modes)
            ),
            runtime_ms=runtime_ms,
        ),
        exclusions=exclusions[:8192],
        tracks=tuple(tracks),
        position_modes=modes,
        evaluation=BlindEvaluationV1(
            reference=reference,
            modes=tuple(
                BlindModeEvaluationV1(
                    rank=mode.rank,
                    horizontal_error_m=reference_error_m(
                        mode.latitude_deg, mode.longitude_deg, reference
                    ),
                )
                for mode in modes
            ),
        )
        if reference is not None
        else None,
        state=result.state,
        reasons=result.reasons,
        diagnostics=diagnostics,
    )


def run_blind_regional(
    root: Path, tle_root: Path, session_id: str, *, output_root: Path | None = None
):
    from leo.analysis.blind_regional_association import solve_blind_regional_association
    from leo.analysis.persistent_hop_trajectory import PersistentHopTrajectoryInputError
    from leo.analysis.research.regional_doppler import Region
    from leo.application.persistent_hop_trajectory import PersistentHopTrajectoryProjectionError
    from leo.operations.blind_tracking_inputs import (
        BlindInputUnavailable,
        prepare_blind_tracking_inputs,
    )
    from leo.operations.tle_archive import TleArchiveReader
    from leo.presentation.blind_regional import render_blind_regional
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    destination = output_root or root
    store = BlindRegionalStore(destination, read_only=False)
    with store.writer(session_id):
        if blind_regional_complete(destination, session_id):
            return store.status(session_id).manifest
        if store.status(session_id).manifest is not None:
            raise ValueError("blind regional publication uses another configuration")
        started = time.monotonic()
        sources = ScannerTrackingInputStore(root)
        try:
            source = sources.load(session_id)
            try:
                prepared = prepare_blind_tracking_inputs(
                    session_id, inputs=sources, archive=TleArchiveReader(tle_root)
                )
            except (
                BlindInputUnavailable,
                PersistentHopTrajectoryInputError,
                PersistentHopTrajectoryProjectionError,
            ) as error:
                input_accounting = getattr(error, "accounting", {})
                document = BlindRegionalDocumentV1(
                    session_id=session_id,
                    input_manifest_sha256=source.input_manifest_sha256,
                    analysis_manifest_sha256=source.analysis_manifest_sha256,
                    configuration_sha256=canonical_digest(configuration()),
                    region=_region(),
                    causal_snapshots=(),
                    accounting=BlindAccountingV1(
                        saved_observation_count=input_accounting.get(
                            "reconstructed_observation_count", 0
                        ),
                        eligible_observation_count=0,
                        track_count=0,
                        associated_track_count=0,
                        excluded_count=1,
                        recorded_exclusion_count=1,
                        runtime_ms=round((time.monotonic() - started) * 1000),
                    ),
                    exclusions=(BlindExclusionV1(scope_id=session_id, reason=str(error)[:256]),),
                    state="insufficient",
                    reasons=(str(error),),
                    diagnostics={"input_accounting": input_accounting},
                )
            else:
                result = solve_blind_regional_association(
                    prepared.numerical_tracks(),
                    region=Region(
                        prepared.region.center_latitude_deg,
                        prepared.region.center_longitude_deg,
                        prepared.region.width_km,
                        prepared.region.height_km,
                    ),
                )
                from leo.cli.scan_position_methods import REFERENCE

                document = evaluated_document(
                    prepared,
                    result,
                    runtime_ms=round((time.monotonic() - started) * 1000),
                    reference=BlindReferenceV1(
                        latitude_deg=REFERENCE.latitude_deg, longitude_deg=REFERENCE.longitude_deg
                    ),
                )
            return store.publish(document, render_blind_regional(document))
        finally:
            sources.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--session-id", required=True)
    args = parser.parse_args()
    manifest = run_blind_regional(
        args.bulk_root, args.tle_root, args.session_id, output_root=args.output_root
    )
    print(json.dumps({"state": "complete", "document": manifest.document.model_dump(mode="json")}))


if __name__ == "__main__":
    main()
