from dataclasses import fields

import pytest

from leo.analysis.standard.analyzers import production_standard_v2_configuration
from leo.analysis.standard.configuration import (
    RECEIVER_STANDARD_RATE_DERIVED_FIELDS,
    parse_receiver_standard_config,
    production_receiver_standard_config,
    production_receiver_standard_stage_configuration,
    production_receiver_standard_waterfall_config,
    require_receiver_standard_sample_rate,
    resolve_receiver_standard_sample_rate,
)
from leo.analysis.standard.runner import receiver_standard_configuration_digest
from leo.contracts.digests import canonical_digest

_LEGACY_PRODUCTION_PATH_CONFIGURATION_DIGEST = (
    "sha256:f3f9b968956a1054e4f75e841311febaacbdb33e0394961dec9d8acb65bf5490"
)
_LEGACY_PRODUCTION_RECEIVER_CONFIGURATION_DIGEST = (
    "sha256:455e7d355bd0e40feff4c6142c8fb1f8631c99fd0480e9a19e908248c46eff1f"
)


def test_shared_production_builder_preserves_frozen_2_5m_json_and_digest() -> None:
    stage_configuration = production_receiver_standard_stage_configuration()
    release_configuration = production_standard_v2_configuration()["path-standard"]
    receiver_configuration = production_receiver_standard_config()

    assert stage_configuration == release_configuration
    assert canonical_digest(stage_configuration) == _LEGACY_PRODUCTION_PATH_CONFIGURATION_DIGEST
    assert (
        receiver_standard_configuration_digest(receiver_configuration)
        == _LEGACY_PRODUCTION_RECEIVER_CONFIGURATION_DIGEST
    )
    assert parse_receiver_standard_config(stage_configuration) == receiver_configuration


def test_production_builder_returns_independent_stage_documents() -> None:
    first = production_receiver_standard_stage_configuration()
    second = production_receiver_standard_stage_configuration()

    first_feedback = first["feedback"]
    assert isinstance(first_feedback, dict)
    first_feedback["maximum_workers"] = 1

    assert first != second
    assert canonical_digest(second) == _LEGACY_PRODUCTION_PATH_CONFIGURATION_DIGEST


@pytest.mark.parametrize("sample_rate_hz", (2_500_000, 3_000_000, 5_000_000))
def test_production_receiver_configuration_resolves_only_explicit_rate_fields(
    sample_rate_hz: int,
) -> None:
    base = production_receiver_standard_config()
    resolved = production_receiver_standard_config(sample_rate_hz=sample_rate_hz)

    assert RECEIVER_STANDARD_RATE_DERIVED_FIELDS == ("replay_gate.sample_rate_hz",)
    assert resolved.replay_gate.sample_rate_hz == sample_rate_hz
    for field in fields(base):
        if field.name != "replay_gate":
            assert getattr(resolved, field.name) == getattr(base, field.name)
    assert resolved.replay_gate.model_dump(exclude={"sample_rate_hz"}) == (
        base.replay_gate.model_dump(exclude={"sample_rate_hz"})
    )
    if sample_rate_hz == 2_500_000:
        assert resolved == base
        assert receiver_standard_configuration_digest(resolved) == (
            _LEGACY_PRODUCTION_RECEIVER_CONFIGURATION_DIGEST
        )
    else:
        assert receiver_standard_configuration_digest(resolved) != (
            _LEGACY_PRODUCTION_RECEIVER_CONFIGURATION_DIGEST
        )


def test_rate_resolution_is_explicit_and_fail_closed() -> None:
    base = production_receiver_standard_config()

    with pytest.raises(ValueError, match="not resolved"):
        require_receiver_standard_sample_rate(base, sample_rate_hz=5_000_000)

    resolved = resolve_receiver_standard_sample_rate(base, sample_rate_hz=5_000_000)
    assert require_receiver_standard_sample_rate(resolved, sample_rate_hz=5_000_000) is resolved
    assert receiver_standard_configuration_digest(resolved) == (
        "sha256:93e589103cc7ede6fc88399b83dadb347577abf3c4e99261fdadeb3e8dca2c21"
    )


@pytest.mark.parametrize(
    ("sample_rate_hz", "expected_fft_samples", "expected_frequency_bins"),
    (
        (2_500_000, 1024, 256),
        (3_000_000, 1232, 308),
        (5_000_000, 2048, 512),
        (10_000_000, 4096, 1024),
        (15_000_000, 6144, 1536),
        (20_000_000, 8192, 2048),
    ),
)
def test_published_waterfall_resolution_is_rate_normalized(
    sample_rate_hz: int,
    expected_fft_samples: int,
    expected_frequency_bins: int,
) -> None:
    config = production_receiver_standard_waterfall_config(sample_rate_hz=sample_rate_hz)

    assert config.fft_samples == expected_fft_samples
    assert config.frequency_bins == expected_frequency_bins
    assert config.fft_samples // config.frequency_bins == 4
