"""Compile editable YAML profiles into immutable content-addressed plans."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_UP
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError

from leo.contracts.digests import canonical_digest
from leo.contracts.profile import (
    CapturePlanV1,
    CapturePlanV2,
    CaptureProfileRevisionV1,
    CaptureProfileRevisionV2,
    CaptureProfileV1,
    CaptureProfileV2,
)
from leo.contracts.states import SourceType, SynchronizationMode


class ProfileDocumentError(ValueError):
    """A profile document is not an unambiguous YAML mapping."""


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as error:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable key",
                key_node.start_mark,
            ) from error
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_profile_revision(path: Path) -> CaptureProfileRevisionV1 | CaptureProfileRevisionV2:
    """Load, normalize, validate, and address one YAML capture profile."""

    try:
        raw = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ProfileDocumentError(f"cannot load capture profile {path}: {error}") from error
    if not isinstance(raw, Mapping):
        raise ProfileDocumentError(f"capture profile {path} must contain one YAML mapping")
    return compile_profile_mapping(raw)


def compile_profile_mapping(
    document: Mapping[str, Any],
) -> CaptureProfileRevisionV1 | CaptureProfileRevisionV2:
    version = document.get("schema_version")
    if version == 1:
        profile = CaptureProfileV1.model_validate(dict(document))
        return CaptureProfileRevisionV1.from_profile(profile)
    if version == 2:
        profile_v2 = CaptureProfileV2.model_validate(dict(document))
        return CaptureProfileRevisionV2.from_profile(profile_v2)
    raise ProfileDocumentError(f"unsupported capture profile schema_version: {version!r}")


def compile_capture_plan(
    revision: CaptureProfileRevisionV1 | CaptureProfileRevisionV2,
    radio_ids: Sequence[str],
    *,
    source_type: SourceType = SourceType.LIVE,
) -> CapturePlanV1 | CapturePlanV2:
    """Resolve a profile duration and synchronization request for selected radios."""

    selected = tuple(radio_ids)
    # Validate count and uniqueness before computing a digest so errors are direct.
    if not 1 <= len(selected) <= 2:
        raise ValueError("a capture plan requires one or two radios")
    if any(not radio_id or len(radio_id) > 128 for radio_id in selected):
        raise ValueError("radio IDs must be non-empty and at most 128 characters")
    if len(set(selected)) != len(selected):
        raise ValueError("capture-plan radio IDs must be unique")

    profile = revision.profile
    if profile.sample_count is not None:
        sample_count = profile.sample_count
    else:
        assert profile.duration_seconds is not None
        sample_count = int(
            (profile.duration_seconds * profile.sample_rate_hz).to_integral_value(
                rounding=ROUND_HALF_UP
            )
        )
        if sample_count <= 0:
            raise ValueError("profile duration resolves to zero samples")

    requested_mode = profile.synchronization_mode
    effective_mode = requested_mode if len(selected) == 2 else SynchronizationMode.NONE
    payload = {
        "schema_version": revision.schema_version,
        "profile_revision": revision.model_dump(mode="json"),
        "radio_ids": list(selected),
        "source_type": source_type.value,
        "resolved_sample_count": sample_count,
        "requested_synchronization_mode": requested_mode.value,
        "effective_synchronization_mode": effective_mode.value,
    }
    plan_type = CapturePlanV2 if revision.schema_version == 2 else CapturePlanV1
    return plan_type(
        plan_digest=canonical_digest(payload),
        profile_revision=revision,
        radio_ids=selected,
        source_type=source_type,
        resolved_sample_count=sample_count,
        requested_synchronization_mode=requested_mode,
        effective_synchronization_mode=effective_mode,
    )
