"""Additional standard position diagnostics from saved tracking, without RF capture."""

import argparse
import json
import math
from dataclasses import asdict
from pathlib import Path

from leo.contracts.digests import canonical_digest
from leo.contracts.position_methods import (
    PositionMethodResultV1,
    PositionMethodsDocumentV1,
    PositionMethodSourceV1,
    ReferencePositionV1,
)
from leo.presentation.position_methods import render_position_method
from leo.storage.position_methods import PositionMethodsStore

REFERENCE = ReferencePositionV1(latitude_deg=37.84903264307456, longitude_deg=-122.4856541910174)


def configuration():
    from leo.analysis.research.formal_orbit import FormalOrbitConfig
    from leo.analysis.research.identity_mixture import MixtureConfig
    from leo.analysis.sparse_scan_position import DEFAULT_REGION

    return json.loads(
        json.dumps(
            {
                "analysis_id": "scanner-position-methods-v1",
                "target_track_limit": 64,
                "rolling_track_limit": 128,
                "history_hours": 8,
                "history_session_limit": 16,
                "observations_per_track_limit": 512,
                "candidate_support": "saved-site-assisted-review-top5-uncertified",
                "partition": "preserve-review-training-membership-v1",
                "reference_evaluation_only": REFERENCE.model_dump(mode="json"),
                "exact_orbit_tolerance_hz": 0.2,
                "phase_state_interpolation": "quartic-five-point-1s-v1",
                "formal_orbit": asdict(FormalOrbitConfig()),
                "identity_mixture": asdict(MixtureConfig()),
                "region": asdict(DEFAULT_REGION),
                "expanded_sigma_hz": 250.0,
            }
        )
    )


def position_methods_complete(
    root: Path, session_id: str, *, expected_input_manifest_sha256: str | None = None
) -> bool:
    store = PositionMethodsStore(root)
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
    for artifact in status.manifest.artifacts:
        store.artifact(session_id, artifact.method)
    return True


def reference_error_m(latitude_deg, longitude_deg, reference):
    """Horizontal great-circle evaluation distance, never used by inference."""
    lat, lon, rlat, rlon = map(
        math.radians, (latitude_deg, longitude_deg, reference.latitude_deg, reference.longitude_deg)
    )
    a = (
        math.sin((lat - rlat) / 2) ** 2
        + math.cos(lat) * math.cos(rlat) * math.sin((lon - rlon) / 2) ** 2
    )
    return 2 * 6_371_008.8 * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def evaluated_result(method, numerical, *, diagnostics=None, reference=REFERENCE):
    """Attach reference error only after the numerical result has been produced."""
    numerical = dict(numerical)
    state = numerical.pop("state", "failed")
    latitude = numerical.pop("latitude_deg", None)
    longitude = numerical.pop("longitude_deg", None)
    reasons = tuple(numerical.pop("reasons", ()))
    if state == "complete":
        state = "diagnostic"
    if state != "diagnostic":
        latitude = longitude = None
        reasons = reasons or ("position-fit-unavailable",)
    return PositionMethodResultV1(
        method=method,
        state=state,
        latitude_deg=latitude,
        longitude_deg=longitude,
        horizontal_error_m=(
            reference_error_m(latitude, longitude, reference)
            if latitude is not None and reference is not None
            else None
        ),
        diagnostics={**numerical, **(diagnostics or {})},
        reasons=reasons,
    )


def run_position_methods(
    root: Path, tle_root: Path, session_id: str, *, output_root: Path | None = None
):
    # Numerical and input preparation imports are intentionally local: queue
    # inventory checks only need the inexpensive immutable manifest reader.
    from leo.analysis.scan_position_methods import (
        fit_expanded_pass_balanced_doppler,
        fit_joint_position_orbit_corrections,
        fit_soft_identity_mixture,
    )
    from leo.analysis.sparse_scan_position import DEFAULT_REGION
    from leo.operations.scan_position_inputs import prepare_scan_position_inputs, verify_orbit_fit
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.scanner_tracking import ScannerTrackingStore
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    destination = output_root if output_root is not None else root
    store = PositionMethodsStore(destination, read_only=False)
    with store.writer(session_id):
        existing = store.status(session_id)
        if existing.manifest is not None:
            if not position_methods_complete(destination, session_id):
                raise ValueError(
                    "position methods configuration changed; use a new analysis version"
                )
            return existing.manifest
        inputs = ScannerTrackingInputStore(root)
        try:
            prepared = prepare_scan_position_inputs(
                session_id,
                inputs=inputs,
                products=ScannerTrackingStore(root),
                archive=TleArchiveReader(tle_root),
            )
        finally:
            inputs.close()
        common = {
            "configuration": configuration(),
            "coordinate_system": "WGS84 geodetic latitude/longitude; altitude fixed at 0 m",
            "reference_error_metric": "horizontal great-circle distance, radius 6371008.8 m",
            "coverage": asdict(prepared.coverage),
            "exclusions": [asdict(item) for item in prepared.exclusions],
            "source_provenance": [asdict(item) for item in prepared.provenance],
            "candidate_support_certified": False,
            "effective_information_warning": (
                "Overlapping receiver paths and within-pass errors are correlated; "
                "raw sample count is not independent information."
            ),
            "evaluation_scope": (
                "Frozen review split; site-conditioned identity shortlist, "
                "not independent identity validation."
            ),
        }
        baseline = fit_expanded_pass_balanced_doppler(
            prepared.target_episodes, DEFAULT_REGION, None
        )
        rolling_seed = fit_expanded_pass_balanced_doppler(prepared.episodes, DEFAULT_REGION, None)
        seed = (rolling_seed.get("east_km"), rolling_seed.get("north_km"))
        if rolling_seed.get("state") not in ("diagnostic", "complete"):
            unavailable = dict(
                state="insufficient", reasons=["rolling-doppler-initialization-unavailable"]
            )
            orbital, mixture = dict(unavailable), dict(unavailable)
        else:
            orbital = fit_joint_position_orbit_corrections(prepared.episodes, DEFAULT_REGION, seed)
            if orbital.get("state") in ("diagnostic", "complete"):
                audit = verify_orbit_fit(prepared, orbital)
                orbital.update(audit)
                maximum_error = audit.get("maximum_absolute_doppler_error_hz")
                orbital["exact_orbit_max_error_hz"] = maximum_error
                passed = maximum_error is not None and maximum_error <= 0.2
                orbital["exact_verification_passed"] = passed
                orbital["diagnostics"]["exact_correction_replay"] = "passed" if passed else "failed"
                if not passed:
                    orbital.update(
                        state="failed", reasons=["exact-orbit-approximation-check-failed"]
                    )
            mixture = fit_soft_identity_mixture(prepared.episodes, DEFAULT_REGION, seed)
        # None of the three numerical functions above has access to REFERENCE.
        methods = tuple(
            evaluated_result(
                name,
                numerical,
                diagnostics={
                    **common,
                    "window_hours": 0 if name == "expanded-doppler" else 8,
                    "cohort_session_count": 1
                    if name == "expanded-doppler"
                    else len(prepared.provenance),
                },
            )
            for name, numerical in (
                ("expanded-doppler", baseline),
                ("orbit-corrected", orbital),
                ("identity-mixture", mixture),
            )
        )
        cohort = tuple(
            PositionMethodSourceV1.model_validate(row) for row in prepared.source_manifest
        )
        document = PositionMethodsDocumentV1(
            session_id=session_id,
            input_manifest_sha256=prepared.target_source.input_manifest_sha256,
            configuration_sha256=canonical_digest(configuration()),
            source_rolling_cohort=cohort,
            source_rolling_cohort_sha256=canonical_digest(
                [c.model_dump(mode="json") for c in cohort]
            ),
            reference_position=REFERENCE,
            methods=methods,
        )
        images = {
            result.method: render_position_method(
                result, session_id=session_id, reference_position=REFERENCE
            )
            for result in methods
        }
        return store.publish(document, images)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--output-root", type=Path, help="Separate local artifact root for replay")
    args = parser.parse_args()
    manifest = run_position_methods(
        args.bulk_root, args.tle_root, args.session_id, output_root=args.output_root
    )
    print(
        json.dumps(
            {
                "state": "complete",
                "session_id": args.session_id,
                "document_sha256": manifest.document_sha256,
                "methods": [
                    {
                        "method": m.method,
                        "state": m.state,
                        "latitude_deg": m.latitude_deg,
                        "longitude_deg": m.longitude_deg,
                        "horizontal_error_m": m.horizontal_error_m,
                    }
                    for m in manifest.document.methods
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
