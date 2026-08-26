from __future__ import annotations

from urllib.parse import quote

import pytest
from pydantic import ValidationError

from leo.contracts.digests import canonical_digest
from leo.presentation.standard_native_artifacts import (
    STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V4,
    STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V4,
    STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V4,
    StandardNativePngArtifactInventoryV4,
    StandardNativePngArtifactV4,
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
