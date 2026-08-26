from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from leo.analysis.research.doppler_association_authority import (
    AUTHORITY_BUNDLE_SCHEMA,
    AuthorityResolverV1,
    CaptureArtifactAuthorityV1,
    CaptureTleAuthorityV1,
    DopplerAssociationAuthorityBundleV1,
    ImmutableStarlinkTleSnapshotV1,
    NominalRfAuthorityV1,
    ObserverSiteAuthorityV1,
    StreamUtcAuthorityV1,
    seal_association_authority_bundle,
)

DIGEST = "sha256:" + "a" * 64
OTHER_DIGEST = "sha256:" + "b" * 64
SESSION_ID = "cap-20260825T150802-473cb5bbcbd6"
COLLECTED_UTC_NS = 1_787_666_532_658_586_719
TARGET_UTC_NS = COLLECTED_UTC_NS + 120_000_000_000


def _capture() -> CaptureArtifactAuthorityV1:
    return CaptureArtifactAuthorityV1(
        session_id=SESSION_ID,
        recording_manifest_uri=f"bulk://recordings/2026/08/25/{SESSION_ID}/manifest.json",
        recording_manifest_sha256=DIGEST,
        analysis_run_id="capture-a5d45dd7752c4fc7833cd017a289f8d7",
        analysis_manifest_uri=(
            f"bulk://analysis/{SESSION_ID}/capture-a5d45dd7752c4fc7833cd017a289f8d7/manifest.json"
        ),
        analysis_manifest_sha256=OTHER_DIGEST,
        raw_integrity_attestation_id="attestation-1",
        episode_id=DIGEST,
        scope_key=OTHER_DIGEST,
        target_mask_digest=DIGEST,
    )


def _resolvers() -> tuple[AuthorityResolverV1, ...]:
    roles = (
        "recording_manifest",
        "analysis_manifest",
        "utc_timing",
        "nominal_rf",
        "observer_site",
        "tle_archive",
    )
    return tuple(
        AuthorityResolverV1(
            role=role,
            implementation_path=(
                "src/leo/operations/tle_archive.py"
                if role == "tle_archive"
                else "src/leo/station/pinned_loader.py"
            ),
            implementation_sha256=DIGEST,
        )
        for role in roles
    )


def _site() -> ObserverSiteAuthorityV1:
    return ObserverSiteAuthorityV1(
        name="station-reviewed-preset",
        latitude_deg=45.5019,
        longitude_deg=-73.5674,
        altitude_m=35.0,
        position_uncertainty_m=5_000.0,
        provenance="Reviewed operator preset; not bound to this capture.",
        source_sha256=DIGEST,
        authority_level="reviewed-preset-not-capture-bound",
        capture_bound_position=False,
        capture_bound_boresight=False,
        absolute_secure_norad_permitted=False,
    )


def _utc() -> StreamUtcAuthorityV1:
    return StreamUtcAuthorityV1(
        session_id=SESSION_ID,
        stream_id="stream-1",
        timing_method="device_counter_anchored",
        sample_rate_hz=2_500_000,
        first_sample_earliest_utc_ns=TARGET_UTC_NS - 1_000_000,
        first_sample_estimate_utc_ns=TARGET_UTC_NS,
        first_sample_latest_utc_ns=TARGET_UTC_NS + 1_000_000,
    )


def _rf() -> NominalRfAuthorityV1:
    return NominalRfAuthorityV1(
        session_id=SESSION_ID,
        stream_id="stream-1",
        radio_id="radio-1",
        receiver_id=1,
        edge="upper",
        applied_if_center_hz=1_800_000_000,
        nominal_lnb_lo_hz=9_750_000_000,
        nominal_sky_frequency_hz=11_550_000_000,
        rf_rule="applied-if-center-plus-nominal-lnb-lo",
        random_tuning_applied_settings_authoritative=True,
        receiver_frequency_reference_calibrated=False,
        lnb_offset_or_drift_measured=False,
    )


def _snapshot(*, collected_utc_ns: int = COLLECTED_UTC_NS) -> ImmutableStarlinkTleSnapshotV1:
    return ImmutableStarlinkTleSnapshotV1(
        source="space-track",
        scope="starlink",
        collected_utc_ns=collected_utc_ns,
        archive_relative_path=(f"archive/space-track/{collected_utc_ns}-{'a' * 64}.tle"),
        snapshot_sha256=DIGEST,
        byte_size=1_000_000,
        satellite_count=8_750,
        tle_epoch_min=datetime(2026, 8, 15, tzinfo=UTC),
        tle_epoch_max=datetime(2026, 8, 25, tzinfo=UTC),
        mutable_index_is_authority=False,
    )


def _tle(*, snapshot: ImmutableStarlinkTleSnapshotV1 | None = None) -> CaptureTleAuthorityV1:
    return CaptureTleAuthorityV1(
        session_id=SESSION_ID,
        target_earliest_utc_ns=TARGET_UTC_NS,
        target_latest_utc_ns=TARGET_UTC_NS + 10_000_000_000,
        snapshot=_snapshot() if snapshot is None else snapshot,
        selection_rule="latest-immutable-starlink-snapshot-collected-before-target",
    )


def _bundle() -> DopplerAssociationAuthorityBundleV1:
    return seal_association_authority_bundle(
        dataset_policy_sha256=DIGEST,
        selector_v2_file_sha256=OTHER_DIGEST,
        selector_v2_manifest_digest=DIGEST,
        captures=(_capture(),),
        resolvers=_resolvers(),
        site=_site(),
        utc=(_utc(),),
        rf=(_rf(),),
        tle=(_tle(),),
    )


def test_bundle_binds_manifests_masks_and_resolvers_separately() -> None:
    bundle = _bundle()

    assert bundle.schema == AUTHORITY_BUNDLE_SCHEMA
    assert bundle.captures[0].recording_manifest_sha256 == DIGEST
    assert bundle.captures[0].analysis_manifest_sha256 == OTHER_DIGEST
    assert bundle.captures[0].target_mask_digest == DIGEST
    assert bundle.resolvers[-1].implementation_path == "src/leo/operations/tle_archive.py"
    assert bundle.resolvers[-1].implementation_sha256 == DIGEST
    assert bundle.tle[0].snapshot.archive_relative_path.startswith("archive/space-track/")
    assert bundle.iq_accessed is False
    assert bundle.response_accessed is False
    assert bundle.satellites_propagated_or_ranked is False


def test_authority_bundle_is_frozen_and_digest_closed() -> None:
    bundle = _bundle()

    with pytest.raises(ValidationError, match="frozen"):
        bundle.response_accessed = True
    with pytest.raises(ValidationError, match="digest"):
        DopplerAssociationAuthorityBundleV1.model_validate(
            {**bundle.model_dump(mode="python"), "dataset_policy_sha256": OTHER_DIGEST}
        )


def test_tle_snapshot_must_be_strictly_causal_and_immutable() -> None:
    late_snapshot = _snapshot(collected_utc_ns=TARGET_UTC_NS)
    with pytest.raises(ValidationError, match="strictly before"):
        _tle(snapshot=late_snapshot)

    snapshot = _snapshot()
    with pytest.raises(ValidationError, match="mutable_index_is_authority"):
        ImmutableStarlinkTleSnapshotV1.model_validate(
            {**snapshot.model_dump(mode="python"), "mutable_index_is_authority": True}
        )
    with pytest.raises(ValidationError, match="archive path"):
        ImmutableStarlinkTleSnapshotV1.model_validate(
            {
                **snapshot.model_dump(mode="python"),
                "archive_relative_path": f"archive/space-track/1-{'a' * 64}.tle",
            }
        )


def test_nominal_rf_cannot_claim_calibration_or_hide_frequency_arithmetic() -> None:
    rf = _rf()
    with pytest.raises(ValidationError, match="receiver_frequency_reference_calibrated"):
        NominalRfAuthorityV1.model_validate(
            {**rf.model_dump(mode="python"), "receiver_frequency_reference_calibrated": True}
        )
    with pytest.raises(ValidationError, match="nominal RF"):
        NominalRfAuthorityV1.model_validate(
            {**rf.model_dump(mode="python"), "nominal_sky_frequency_hz": 12_000_000_000}
        )


def test_site_preset_cannot_authorize_secure_norad_claims() -> None:
    site = _site()
    with pytest.raises(ValidationError, match="absolute_secure_norad_permitted"):
        ObserverSiteAuthorityV1.model_validate(
            {**site.model_dump(mode="python"), "absolute_secure_norad_permitted": True}
        )


def test_capture_inventories_and_resolver_order_fail_closed() -> None:
    bundle = _bundle()
    foreign_utc = _utc().model_copy(update={"session_id": "cap-foreign"})
    with pytest.raises(ValidationError, match="inventories disagree"):
        DopplerAssociationAuthorityBundleV1.model_validate(
            {
                **bundle.model_dump(mode="python"),
                "utc": [foreign_utc.model_dump(mode="python")],
            }
        )

    reversed_resolvers = tuple(reversed(_resolvers()))
    with pytest.raises(ValidationError, match="resolver roles or order"):
        seal_association_authority_bundle(
            dataset_policy_sha256=DIGEST,
            selector_v2_file_sha256=OTHER_DIGEST,
            selector_v2_manifest_digest=DIGEST,
            captures=(_capture(),),
            resolvers=reversed_resolvers,
            site=_site(),
            utc=(_utc(),),
            rf=(_rf(),),
            tle=(_tle(),),
        )


def test_resolver_path_cannot_escape_repository() -> None:
    with pytest.raises(ValidationError, match="repository-relative"):
        AuthorityResolverV1(
            role="tle_archive",
            implementation_path="../outside.py",
            implementation_sha256=DIGEST,
        )
