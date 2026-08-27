from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from leo.analysis.research import long_arc_catalogue_adapter as adapter_module
from leo.analysis.research.long_arc_catalogue_adapter import (
    LongArcAdapterInputError,
    build_registered_long_arc_graph,
    load_registered_long_arc_graph,
)
from leo.analysis.research.long_arc_dataset import (
    PostFixLongArcCohortV1,
    load_post_fix_long_arc_cohort,
)
from leo.analysis.research.satellite_pnt_long_arc_protocol import (
    SatellitePntLongArcProtocolV1,
    load_satellite_pnt_long_arc_protocol,
)

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = ROOT / "config/analysis/satellite-pnt-long-arc-development-protocol-v1.json"
ARC_9981 = "long-arc-9981-r19f2-s1-rx1-upper-0-30s"
ARC_150802 = "long-arc-150802-r19f2-s1-rx1-upper-37p575-51p4s"


def _authority() -> tuple[SatellitePntLongArcProtocolV1, PostFixLongArcCohortV1]:
    protocol = load_satellite_pnt_long_arc_protocol(PROTOCOL_PATH, repository_root=ROOT)
    cohort = load_post_fix_long_arc_cohort(ROOT / protocol.registry.path)
    return protocol, cohort


@pytest.mark.parametrize(
    (
        "arc_id",
        "expected_count",
        "graph_digest",
        "support_digest",
        "receipt_digest",
        "first_cfo_hz",
        "last_cfo_hz",
    ),
    (
        (
            ARC_9981,
            881,
            "sha256:086f008ad13fd4ca6742096f02932c01145659b6210d33b63a4274d99dfc4d60",
            "sha256:e4d8d50702dd9c993afddc35fe09c0e2371ce9a03a7f215298a6d1a09ce11a36",
            "sha256:146c8f46cc6dda66ac20d1236d40a1083bc058bb26e69e9c2b4f39f78e1baa5a",
            -114925.85,
            -218409.19,
        ),
        (
            ARC_150802,
            550,
            "sha256:e336e038b383b3e06e17d86b57122dd0a844abf98b2bf869b949211d7c1bd947",
            "sha256:542b04293726b17083d37f7a2b39543f92d13c9947616871379b81fd6a72b7cb",
            "sha256:fae4e734f9f958cf6fd7367e3a176cabd3d2b9e44aeae41edc1c26e91e602c40",
            -94019.23971092782,
            -143182.08639018858,
        ),
    ),
)
def test_exact_registered_graphs_reproduce_without_iq_or_propagation(
    arc_id: str,
    expected_count: int,
    graph_digest: str,
    support_digest: str,
    receipt_digest: str,
    first_cfo_hz: float,
    last_cfo_hz: float,
) -> None:
    bundle = load_registered_long_arc_graph(
        PROTOCOL_PATH,
        repository_root=ROOT,
        arc_id=arc_id,
    )

    assert len(bundle.graph.observations) == expected_count
    assert bundle.graph.content_digest == graph_digest
    assert bundle.prediction_support.content_digest == support_digest
    assert bundle.receipt_digest == receipt_digest
    assert bundle.graph.observations[0].measured_cfo_hz == first_cfo_hz
    assert bundle.graph.observations[-1].measured_cfo_hz == last_cfo_hz
    assert bundle.response_accessed_to_construct_graph is True
    assert bundle.response_exposed_to_prediction_port is False
    assert bundle.iq_accessed is False
    assert bundle.tle_propagation_run is False
    assert bundle.association_scored is False


def test_prediction_support_projection_contains_no_cfo_or_source_response_fields() -> None:
    bundle = load_registered_long_arc_graph(
        PROTOCOL_PATH,
        repository_root=ROOT,
        arc_id=ARC_150802,
    )
    dumped = bundle.prediction_support.model_dump_json()

    assert "measured_cfo_hz" not in dumped
    assert "standard_uncertainty_hz" not in dumped
    assert "source_binding_digest" not in dumped
    assert "receiver_path_id" not in dumped
    assert bundle.prediction_support.response_fields_excluded is True
    assert tuple(item.observation_id for item in bundle.prediction_support.observations) == tuple(
        item.observation_id for item in bundle.graph.observations
    )


def test_support_geometry_is_centred_and_source_windows_do_not_overlap() -> None:
    first_bundle = load_registered_long_arc_graph(
        PROTOCOL_PATH,
        repository_root=ROOT,
        arc_id=ARC_9981,
    )
    second_bundle = load_registered_long_arc_graph(
        PROTOCOL_PATH,
        repository_root=ROOT,
        arc_id=ARC_150802,
    )

    assert first_bundle.graph.observations[0].support_center_utc_ns == 1787599375422378414
    assert second_bundle.graph.observations[0].support_center_utc_ns == 1787670523165078492
    first_moments = first_bundle.graph.observations[0].factorial_support_moments_s
    assert first_moments[:2] == (1.0, 0.0)
    assert first_moments[2] == pytest.approx(1.6666666659999996e-05)
    assert first_moments[3] == 0.0
    assert second_bundle.graph.observations[0].factorial_support_moments_s[1] == pytest.approx(
        1.0 / 3_000_000_000,
        abs=1e-20,
    )
    for bundle in (first_bundle, second_bundle):
        rows = bundle.graph.observations
        assert all(
            right.source_sample_start >= left.source_sample_end
            for left, right in zip(rows, rows[1:], strict=False)
        )
        assert all(
            row.support_start_utc_ns <= row.support_center_utc_ns < row.support_end_utc_ns
            for row in rows
        )


def test_payload_tamper_fails_before_graph_construction() -> None:
    protocol, cohort = _authority()
    observation = protocol.observations[0]
    payload = (ROOT / observation.cfo_evidence.path).read_bytes()
    poisoned = payload.replace(b"-114925.85", b"-114925.86", 1)
    assert poisoned != payload

    with pytest.raises(LongArcAdapterInputError, match="digest"):
        build_registered_long_arc_graph(
            protocol,
            cohort,
            arc_id=ARC_9981,
            cfo_evidence_payload=poisoned,
            timing_authority_payload=poisoned,
        )


def test_nested_model_copy_poison_is_revalidated() -> None:
    protocol, cohort = _authority()
    poisoned_models = protocol.models.model_copy(update={"observation_sigma_hz": 75.0})
    poisoned_protocol = protocol.model_copy(update={"models": poisoned_models})
    observation = protocol.observations[0]
    payload = (ROOT / observation.cfo_evidence.path).read_bytes()

    with pytest.raises(LongArcAdapterInputError, match="protocol document"):
        build_registered_long_arc_graph(
            poisoned_protocol,
            cohort,
            arc_id=ARC_9981,
            cfo_evidence_payload=payload,
            timing_authority_payload=payload,
        )


def test_adapter_has_no_iq_storage_propagation_or_association_import() -> None:
    source = inspect.getsource(adapter_module)
    assert "leo.storage" not in source
    assert "leo.infrastructure" not in source
    assert "propagate_grid" not in source
    assert "catalogue_association import associate" not in source
    assert "read_iq" not in source
    assert "/mnt/qnap01" not in source
