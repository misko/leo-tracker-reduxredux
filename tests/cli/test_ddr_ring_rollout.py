from pathlib import Path

import pytest

from leo.acquisition.mixed_rate_schedule import (
    compile_production_dwell_intent_hold_rollout_v1,
    compile_production_dwell_intent_v2,
)
from leo.cli.backend import CliBackendError
from leo.cli.composition import CliSettings, LocalAcquisitionBackend
from leo.domain.mixed_rate_capture import (
    compile_production_capture_plan_v4,
    compile_production_capture_plan_v5,
)
from leo.domain.profiles import load_profile_revision


@pytest.mark.parametrize("maximum", [0, 10_000_000, 15_000_000, 20_000_000])
def test_rollout_selects_only_qualified_high_rate_profiles(tmp_path, maximum):
    settings = CliSettings.from_environ(
        {
            "LEO_PROFILE_ROOT": str(Path(__file__).parents[2] / "profiles"),
            "LEO_BULK_ROOT": str(tmp_path),
            "LEO_DDR_RING_MAX_RATE_HZ": str(maximum),
        }
    )
    authority = LocalAcquisitionBackend(settings).production_profile_authority()
    for (rate, _receivers, _mixed), (name, digest, refill) in authority.items():
        expected = rate > 5_000_000 and rate <= maximum
        assert ("ddr-ring-v6" in name) is expected
        assert refill == (1_000_000 if expected else 1_048_576)
        assert digest.startswith("sha256:")


def test_rollout_defaults_off_and_rejects_ambiguous_limit():
    assert CliSettings.from_environ({}).ddr_ring_max_rate_hz == 0
    with pytest.raises(CliBackendError, match="DDR ring rollout maximum"):
        CliSettings.from_environ({"LEO_DDR_RING_MAX_RATE_HZ": "12000000"})


@pytest.mark.parametrize(
    "receiver,digest",
    [
        (0, "sha256:91ee768cb8d96ae7c6e0462c91585847e504db1c9e66a96ceec08469d13d2a18"),
        (1, "sha256:2f08108db6f9ed5c8e9b259c23ecb1c9b11376a72f2c1ff234c152b8efe84db4"),
    ],
)
def test_25m_production_authority_selects_the_zero_external_prime_v8_profile(
    tmp_path, receiver, digest
):
    settings = CliSettings.from_environ(
        {
            "LEO_PROFILE_ROOT": str(Path(__file__).parents[2] / "profiles"),
            "LEO_BULK_ROOT": str(tmp_path),
        }
    )

    name, actual_digest, refill = LocalAcquisitionBackend(settings).production_profile_authority()[
        (25_000_000, (receiver,), True)
    ]

    assert name == f"starlink-ch4-lower-25m-60s-rx{receiver}-direct-async-v8"
    assert actual_digest == digest
    assert refill == 1_048_576


@pytest.mark.parametrize(
    ("rate", "receiver", "digest"),
    [
        (10, 0, "sha256:b08edacbbfafcfd525e9320c2a582503751d851a8bb5b8c2a58cf3997ff132ce"),
        (15, 1, "sha256:8b92ea68da761389ff0ae64844f85af3f7c2e6c4c5245627d79cb52e261cd30c"),
        (20, 0, "sha256:0fe7aec03eb65de32693327f29527a6f6342ee93a875169324ef9cfa2fa670a6"),
        (25, 1, "sha256:1e631a4adbc892e9fb2d610c795953d22db8cbb15485767785b23fdaa9b4c64e"),
    ],
)
def test_direct_async_rollout_selects_one_session_exact_dma_drop_geometry(
    tmp_path, rate, receiver, digest
):
    settings = CliSettings.from_environ(
        {
            "LEO_PROFILE_ROOT": str(Path(__file__).parents[2] / "profiles"),
            "LEO_BULK_ROOT": str(tmp_path),
            "LEO_DIRECT_ASYNC_ENABLED": "1",
        }
    )

    name, actual_digest, refill = LocalAcquisitionBackend(settings).production_profile_authority()[
        (rate * 1_000_000, (receiver,), True)
    ]

    assert name == (f"starlink-ch4-lower-{rate}m-60s-rx{receiver}-direct-async-exact-dma-drop-v12")
    assert actual_digest == digest
    assert refill == 1_000_000


def test_acquisition_identity_does_not_change_analysis_worker_identity():
    settings = CliSettings.from_environ(
        {
            "LEO_PIPELINE_RELEASE_ID": "a" * 40,
            "LEO_ACQUISITION_RELEASE_ID": "b" * 40,
        }
    )
    assert settings.pipeline_release_id == "a" * 40
    assert LocalAcquisitionBackend(settings)._acquisition_producer().source_revision == "b" * 40
    legacy = CliSettings.from_environ({"LEO_PIPELINE_RELEASE_ID": "a" * 40})
    assert LocalAcquisitionBackend(legacy)._acquisition_producer().source_revision == "a" * 40


def test_ring_profile_authority_compiles_each_unchanged_production_intent(tmp_path):
    root = Path(__file__).parents[2] / "profiles"
    settings = CliSettings.from_environ(
        {
            "LEO_PROFILE_ROOT": str(root),
            "LEO_BULK_ROOT": str(tmp_path),
            "LEO_DDR_RING_MAX_RATE_HZ": "20000000",
        }
    )
    authority = LocalAcquisitionBackend(settings).production_profile_authority()
    for ordinal in range(8):
        intent = compile_production_dwell_intent_v2(
            operation_key=f"ring-test-{ordinal}",
            cadence_ordinal=ordinal,
            radio_ids=("radio-a", "radio-b"),
            profile_authority=authority,
        )
        revisions = {
            leg.radio_id: load_profile_revision(root / f"{leg.profile_name}.yaml")
            for leg in intent.radio_legs
        }
        plan = compile_production_capture_plan_v4(
            intent=intent,
            profile_revisions_by_radio=revisions,
        )
        assert plan.schema_version == 4
        assert plan.scheduled_intent_digest == intent.intent_digest


def test_exact_dma_drop_authority_compiles_actual_capture_plans(tmp_path):
    root = Path(__file__).parents[2] / "profiles"
    settings = CliSettings.from_environ(
        {
            "LEO_PROFILE_ROOT": str(root),
            "LEO_BULK_ROOT": str(tmp_path),
            "LEO_DIRECT_ASYNC_ENABLED": "1",
        }
    )
    authority = LocalAcquisitionBackend(settings).production_profile_authority()

    for ordinal in range(6):
        intent = compile_production_dwell_intent_hold_rollout_v1(
            operation_key=f"exact-dma-drop-{ordinal}",
            cadence_ordinal=ordinal,
            radio_ids=("radio-a", "radio-b"),
            profile_authority=authority,
        )
        plan = compile_production_capture_plan_v5(
            intent=intent,
            profile_revisions_by_radio={
                leg.radio_id: load_profile_revision(root / f"{leg.profile_name}.yaml")
                for leg in intent.radio_legs
            },
        )

        assert plan.schema_version == 5
        assert any(
            "DEVICE_BUFFER:DIRECT_ASYNC_EXACT_DMA_DROP_V5" in leg.profile_revision.profile.tags
            for leg in plan.radio_plans
        )
