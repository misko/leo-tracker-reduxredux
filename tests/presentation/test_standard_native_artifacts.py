from __future__ import annotations

from urllib.parse import quote

import pytest
from pydantic import ValidationError

from leo.contracts.digests import canonical_digest
from leo.presentation.standard_native_artifacts import (
    STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V4,
    STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V7,
    STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V8,
    STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V10,
    STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V11,
    STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V4,
    STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V8,
    STANDARD_NATIVE_PAIRED_ARTIFACT_NAMES_V11,
    STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V4,
    STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V8,
    STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V10,
    StandardNativePngArtifactInventoryV4,
    StandardNativePngArtifactInventoryV6,
    StandardNativePngArtifactInventoryV7,
    StandardNativePngArtifactInventoryV8,
    StandardNativePngArtifactInventoryV10,
    StandardNativePngArtifactInventoryV11,
    StandardNativePngArtifactV4,
    StandardNativePngArtifactV8,
    StandardNativePngArtifactV10,
    StandardNativePngArtifactV11,
)
from leo.presentation.standard_pipeline import StandardSubjectKindV2


def _inventory(
    kind: StandardSubjectKindV2,
) -> StandardNativePngArtifactInventoryV4:
    session_id = "cap-native-artifacts"
    subject_id = "path:radio-0:rx0" if kind is StandardSubjectKindV2.RECEIVER_PATH else "radio:0"
    names = (
        STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V4
        if kind is StandardSubjectKindV2.RECEIVER_PATH
        else STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V4
    )
    base = (
        f"/api/v2/recordings/{quote(session_id, safe='')}/standard-subjects/"
        f"{quote(subject_id, safe='')}"
    )
    artifacts = []
    for index, name in enumerate(names):
        label, description, catalog_kind, schema_version, view_name = (
            STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V4[name]
        )
        artifacts.append(
            StandardNativePngArtifactV4(
                name=name,
                label=label,
                description=description,
                href=(
                    f"{base}/views/{view_name}.png"
                    if view_name is not None
                    else f"{base}/artifacts/{name}.png"
                ),
                catalog_kind=catalog_kind,
                product_schema_version=schema_version,
                digest=canonical_digest({"artifact": name}),
                byte_size=1000 + index,
            )
        )
    values = {
        "schema_version": 4,
        "session_id": session_id,
        "subject_id": subject_id,
        "subject_kind": kind.value,
        "run_id": "run-native-artifacts",
        "run_manifest_digest": canonical_digest({"manifest": "native"}),
        "sample_rate_hz": 5_000_000,
        "coverage_status": "partial_coverage",
        "artifacts": tuple(item.model_dump(mode="json") for item in artifacts),
    }
    return StandardNativePngArtifactInventoryV4(
        session_id=session_id,
        subject_id=subject_id,
        subject_kind=kind,
        run_id="run-native-artifacts",
        run_manifest_digest=values["run_manifest_digest"],
        sample_rate_hz=5_000_000,
        coverage_status="partial_coverage",
        artifacts=tuple(artifacts),
        content_digest=canonical_digest(values),
    )


@pytest.mark.parametrize(
    ("kind", "expected"),
    (
        (StandardSubjectKindV2.RECEIVER_PATH, STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V4),
        (StandardSubjectKindV2.RADIO, STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V4),
        (StandardSubjectKindV2.PAIRED, STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V4),
    ),
)
def test_native_png_inventory_is_exact_11_5_5(
    kind: StandardSubjectKindV2,
    expected: tuple[str, ...],
) -> None:
    inventory = _inventory(kind)

    assert tuple(item.name for item in inventory.artifacts) == expected
    assert all(item.media_type == "image/png" for item in inventory.artifacts)
    assert all("%3A" in item.href for item in inventory.artifacts)


@pytest.mark.parametrize("mutation", ("drop", "swap", "wrong-href", "wrong-digest"))
def test_native_png_inventory_rejects_incomplete_or_crossed_rows(mutation: str) -> None:
    document = _inventory(StandardSubjectKindV2.RECEIVER_PATH).model_dump(mode="json")
    artifacts = document["artifacts"]
    assert isinstance(artifacts, list)
    if mutation == "drop":
        artifacts.pop()
    elif mutation == "swap":
        artifacts[0], artifacts[1] = artifacts[1], artifacts[0]
    elif mutation == "wrong-href":
        artifacts[0]["href"] = (
            "/api/v2/recordings/foreign/standard-subjects/foreign/views/waterfall.png"
        )
    else:
        document["content_digest"] = canonical_digest({"foreign": True})

    with pytest.raises(ValidationError):
        StandardNativePngArtifactInventoryV4.model_validate(document)


def test_production_png_inventory_accepts_twenty_msps_without_weakening_v5() -> None:
    source = _inventory(StandardSubjectKindV2.PAIRED)
    values = source.model_dump(mode="json", exclude={"schema_version", "sample_rate_hz"})
    values["schema_version"] = 6
    values["sample_rates_hz"] = (2_500_000, 20_000_000)
    values["content_digest"] = canonical_digest(
        {key: value for key, value in values.items() if key != "content_digest"}
    )

    inventory = StandardNativePngArtifactInventoryV6.model_validate(values)

    assert inventory.sample_rates_hz == (2_500_000, 20_000_000)


def test_additive_phase_inventory_preserves_old_png_identity() -> None:
    legacy = _inventory(StandardSubjectKindV2.RECEIVER_PATH)
    legacy_pilot_versions = tuple(
        item.product_schema_version
        for item in legacy.artifacts
        if item.name.startswith("pilot-") and item.name != "pilot-methods"
    )
    assert legacy_pilot_versions == (3, 3, 3)

    artifacts = tuple(
        item.model_copy(
            update={
                "label": STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V7[item.name][0],
                "description": STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V7[item.name][1],
                "catalog_kind": STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V7[item.name][2],
                "product_schema_version": STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V7[item.name][3],
            }
        )
        for item in legacy.artifacts
    )
    values = {
        "schema_version": 7,
        "session_id": legacy.session_id,
        "subject_id": legacy.subject_id,
        "subject_kind": legacy.subject_kind.value,
        "run_id": legacy.run_id,
        "run_manifest_digest": legacy.run_manifest_digest,
        "sample_rates_hz": (5_000_000,),
        "coverage_status": legacy.coverage_status,
        "artifacts": tuple(item.model_dump(mode="json") for item in artifacts),
    }
    phase = StandardNativePngArtifactInventoryV7.model_validate(
        {**values, "content_digest": canonical_digest(values)}
    )

    assert tuple(
        item.product_schema_version
        for item in phase.artifacts
        if item.name.startswith("pilot-") and item.name != "pilot-methods"
    ) == (4, 4, 4)


@pytest.mark.parametrize(
    ("kind", "expected_names"),
    (
        (StandardSubjectKindV2.RECEIVER_PATH, STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V8),
        (StandardSubjectKindV2.RADIO, STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V8),
        (StandardSubjectKindV2.PAIRED, STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V8),
    ),
)
def test_additive_doppler_inventory_is_exact_and_keeps_v7_readable(
    kind: StandardSubjectKindV2,
    expected_names: tuple[str, ...],
) -> None:
    legacy = _inventory(kind)
    session_id = legacy.session_id
    subject_id = legacy.subject_id
    base = (
        f"/api/v2/recordings/{quote(session_id, safe='')}/standard-subjects/"
        f"{quote(subject_id, safe='')}"
    )
    artifacts = []
    for index, name in enumerate(expected_names):
        label, description, catalog_kind, schema_version, view_name = (
            STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V8[name]
        )
        artifacts.append(
            StandardNativePngArtifactV8(
                name=name,
                label=label,
                description=description,
                href=(
                    f"{base}/views/{view_name}.png"
                    if view_name is not None
                    else f"{base}/artifacts/{name}.png"
                ),
                catalog_kind=catalog_kind,
                product_schema_version=schema_version,
                digest=canonical_digest({"v8-artifact": name}),
                byte_size=2000 + index,
            )
        )
    values = {
        "schema_version": 8,
        "session_id": session_id,
        "subject_id": subject_id,
        "subject_kind": kind.value,
        "run_id": legacy.run_id,
        "run_manifest_digest": legacy.run_manifest_digest,
        "sample_rates_hz": (2_500_000, 10_000_000),
        "coverage_status": legacy.coverage_status,
        "artifacts": tuple(item.model_dump(mode="json") for item in artifacts),
    }

    inventory = StandardNativePngArtifactInventoryV8.model_validate(
        {**values, "content_digest": canonical_digest(values)}
    )

    assert tuple(item.name for item in inventory.artifacts) == expected_names
    assert inventory.artifacts[1].catalog_kind == "standard.doppler-waterfall-png"
    assert StandardNativePngArtifactInventoryV4.model_validate(legacy.model_dump()) == legacy


def test_additive_epoch_inventory_is_path_only_and_keeps_v8_readable() -> None:
    legacy = _inventory(StandardSubjectKindV2.RECEIVER_PATH)
    base = (
        f"/api/v2/recordings/{quote(legacy.session_id, safe='')}/standard-subjects/"
        f"{quote(legacy.subject_id, safe='')}"
    )
    artifacts = []
    for index, name in enumerate(STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V10):
        label, description, catalog_kind, schema_version, view_name = (
            STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V10[name]
        )
        artifacts.append(
            StandardNativePngArtifactV10(
                name=name,
                label=label,
                description=description,
                href=(
                    f"{base}/views/{view_name}.png"
                    if view_name is not None
                    else f"{base}/artifacts/{name}.png"
                ),
                catalog_kind=catalog_kind,
                product_schema_version=schema_version,
                digest=canonical_digest({"v10-artifact": name}),
                byte_size=3000 + index,
            )
        )
    values = {
        "schema_version": 10,
        "session_id": legacy.session_id,
        "subject_id": legacy.subject_id,
        "subject_kind": StandardSubjectKindV2.RECEIVER_PATH.value,
        "run_id": legacy.run_id,
        "run_manifest_digest": legacy.run_manifest_digest,
        "sample_rates_hz": (2_500_000,),
        "coverage_status": legacy.coverage_status,
        "artifacts": tuple(item.model_dump(mode="json") for item in artifacts),
    }

    inventory = StandardNativePngArtifactInventoryV10.model_validate(
        {**values, "content_digest": canonical_digest(values)}
    )

    assert tuple(item.name for item in inventory.artifacts) == (
        STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V10
    )
    assert tuple(item.name for item in inventory.artifacts[9:11]) == (
        "glrt-epoch-timing",
        "glrt-epoch-rate",
    )
    assert StandardNativePngArtifactInventoryV4.model_validate(legacy.model_dump()) == legacy


def test_additive_v11_inventory_closes_the_exact_low_radio_2p5_x25_comparison() -> None:
    session_id = "cap-native-paired-comparison"
    subject_id = "radio:stream-low:radio-low"
    base = (
        f"/api/v2/recordings/{quote(session_id, safe='')}/standard-subjects/"
        f"{quote(subject_id, safe='')}"
    )
    artifacts = []
    for index, name in enumerate(STANDARD_NATIVE_PAIRED_ARTIFACT_NAMES_V11):
        label, description, catalog_kind, schema_version, view_name = (
            STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V11[name]
        )
        artifacts.append(
            StandardNativePngArtifactV11(
                name=name,
                label=label,
                description=description,
                href=(
                    f"{base}/views/{view_name}.png"
                    if view_name is not None
                    else f"{base}/artifacts/{name}.png"
                ),
                catalog_kind=catalog_kind,
                product_schema_version=schema_version,
                digest=canonical_digest({"v11-artifact": name}),
                byte_size=4000 + index,
            )
        )
    values = {
        "schema_version": 11,
        "session_id": session_id,
        "subject_id": subject_id,
        "subject_kind": StandardSubjectKindV2.RADIO.value,
        "run_id": "run-native-paired-comparison",
        "run_manifest_digest": canonical_digest({"v11": "manifest"}),
        "sample_rates_hz": (2_500_000, 25_000_000),
        "coverage_status": "partial_coverage",
        "artifacts": tuple(item.model_dump(mode="json") for item in artifacts),
    }

    inventory = StandardNativePngArtifactInventoryV11.model_validate(
        {**values, "content_digest": canonical_digest(values)}
    )

    assert tuple(item.name for item in inventory.artifacts) == (
        STANDARD_NATIVE_PAIRED_ARTIFACT_NAMES_V11
    )
    assert inventory.artifacts[-1].catalog_kind == ("standard.pss-glrt-frame-comparison-png")
    tampered = inventory.model_dump(mode="json")
    tampered["sample_rates_hz"] = [2_500_000, 15_000_000]
    with pytest.raises(ValidationError):
        StandardNativePngArtifactInventoryV11.model_validate(tampered)
