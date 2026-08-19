from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from leo.contracts.states import RadioTransport
from leo.station.authority import (
    CaptureHardwareBindingV1,
    CapturePathSelectorV1,
    FixturePathAuthorityV1,
    FixtureStreamPathInventoryV1,
    RadioEndpointEvidenceV1,
    StationRadioTopologyV1,
    StationReceiverAssignmentV1,
    StationReceiverTopologyV1,
)

_DIGEST_A = f"sha256:{'1' * 64}"
_DIGEST_B = f"sha256:{'2' * 64}"


def _assignment(
    receiver_id: int,
    *,
    radio: str = "a",
    start: int = 1_000,
    end: int = 2_000,
    epoch: str | None = None,
) -> StationReceiverAssignmentV1:
    return StationReceiverAssignmentV1(
        receiver_id=receiver_id,
        physical_receiver_id=f"physical-{radio}-rx{receiver_id}",
        hardware_epoch_external_id=epoch or f"hardware-{radio}-rx{receiver_id}-v1",
        valid_from_utc_ns=start,
        valid_until_utc_ns=end,
    )


def _radio(
    name: str,
    *,
    assignments: tuple[StationReceiverAssignmentV1, ...] | None = None,
    endpoint: str | None = None,
    evidence_digest: str = _DIGEST_A,
) -> StationRadioTopologyV1:
    return StationRadioTopologyV1.create(
        radio_id=f"radio-{name}",
        radio_serial=f"serial-{name}",
        endpoint_evidence=RadioEndpointEvidenceV1(
            transport=RadioTransport.IIO_IP,
            endpoint=endpoint or f"ip:192.0.2.{10 + ord(name) - ord('a')}",
            evidence_uri=f"authority/radio-{name}.json",
            evidence_digest=evidence_digest,
        ),
        receiver_assignments=assignments
        or (_assignment(0, radio=name), _assignment(1, radio=name)),
    )


def _topology(*radios: StationRadioTopologyV1) -> StationReceiverTopologyV1:
    return StationReceiverTopologyV1.create(
        station_id="station-gauss",
        topology_revision="gauss-receiver-map-v1",
        valid_from_utc_ns=1_000,
        valid_until_utc_ns=2_000,
        radios=radios or (_radio("a"),),
    )


def _binding(topology: StationReceiverTopologyV1) -> CaptureHardwareBindingV1:
    radio = topology.radios[0]
    return CaptureHardwareBindingV1.create(
        session_id="session-a",
        manifest_digest=_DIGEST_B,
        capture_start_utc_ns=1_100,
        capture_end_utc_ns=1_900,
        topology=topology,
        selectors=(
            CapturePathSelectorV1(
                stream_id="stream-a",
                radio_id=radio.radio_id,
                radio_serial=radio.radio_serial,
                receiver_id=1,
            ),
            CapturePathSelectorV1(
                stream_id="stream-a",
                radio_id=radio.radio_id,
                radio_serial=radio.radio_serial,
                receiver_id=0,
            ),
        ),
    )


def test_topology_factory_canonicalizes_complete_inventory_and_digest() -> None:
    topology = _topology(_radio("b"), _radio("a"))

    assert tuple(item.radio_id for item in topology.radios) == ("radio-a", "radio-b")
    assert tuple(
        item.receiver_id for item in topology.radios[0].receiver_assignments
    ) == (0, 1)
    assert topology.topology_digest.startswith("sha256:")
    assert StationReceiverTopologyV1.model_validate(topology.model_dump(mode="json")) == topology


def test_topology_rejects_noncanonical_radio_and_assignment_order() -> None:
    radio = _radio("a")
    reversed_radio = radio.model_dump(mode="python")
    reversed_radio["receiver_assignments"] = tuple(
        reversed(reversed_radio["receiver_assignments"])
    )
    with pytest.raises(ValidationError, match="canonical receiver/time order"):
        StationRadioTopologyV1.model_validate(reversed_radio)

    topology = _topology(_radio("a"), _radio("b"))
    reversed_topology = topology.model_dump(mode="python")
    reversed_topology["radios"] = tuple(reversed(reversed_topology["radios"]))
    with pytest.raises(ValidationError, match="canonical identity order"):
        StationReceiverTopologyV1.model_validate(reversed_topology)


def test_topology_rejects_partial_radio_inventory() -> None:
    with pytest.raises(ValidationError, match="cannot omit RX0 or RX1"):
        _radio("a", assignments=(_assignment(0),))


def test_topology_rejects_overlapping_gapped_and_inexact_intervals() -> None:
    overlap = (
        _assignment(0, start=1_000, end=1_600, epoch="epoch-0a"),
        _assignment(0, start=1_500, end=2_000, epoch="epoch-0b"),
        _assignment(1),
    )
    with pytest.raises(ValidationError, match="overlap"):
        _radio("a", assignments=overlap)

    gap = (
        _assignment(0, start=1_000, end=1_400, epoch="epoch-0a"),
        _assignment(0, start=1_500, end=2_000, epoch="epoch-0b"),
        _assignment(1),
    )
    with pytest.raises(ValidationError, match="exactly contiguous"):
        _topology(_radio("a", assignments=gap))

    short = (_assignment(0, start=1_100), _assignment(1))
    with pytest.raises(ValidationError, match="full topology interval"):
        _topology(_radio("a", assignments=short))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda document: document["radios"][0].__setitem__("radio_serial", "forged"),
        lambda document: document["radios"][0]["endpoint_evidence"].__setitem__(
            "endpoint", "ip:203.0.113.99"
        ),
        lambda document: document["radios"][0]["receiver_assignments"][0].__setitem__(
            "physical_receiver_id", "forged-path"
        ),
        lambda document: document["radios"][0]["receiver_assignments"][0].__setitem__(
            "hardware_epoch_external_id", "forged-epoch"
        ),
    ],
)
def test_topology_content_digest_rejects_identity_forgery(
    mutate: Any,
) -> None:
    document = _topology(_radio("a")).model_dump(mode="python")
    mutate(document)

    with pytest.raises(ValidationError, match="digest does not match content"):
        StationReceiverTopologyV1.model_validate(document)


def test_topology_rejects_duplicate_inventory_identities() -> None:
    first = _radio("a")
    duplicate = StationRadioTopologyV1.create(
        radio_id="radio-b",
        radio_serial=first.radio_serial,
        endpoint_evidence=first.endpoint_evidence,
        receiver_assignments=(
            _assignment(0, radio="b"),
            _assignment(1, radio="b"),
        ),
    )
    with pytest.raises(ValidationError, match="serials must be unique"):
        _topology(first, duplicate)


def test_capture_binding_resolves_exact_paths_and_rejects_retargeted_authority() -> None:
    topology = _topology(_radio("a"))
    binding = _binding(topology)

    assert tuple(item.receiver_id for item in binding.paths) == (0, 1)
    assert binding.paths[0].physical_receiver_id == "physical-a-rx0"
    assert binding.paths[0].hardware_epoch_external_id == "hardware-a-rx0-v1"
    binding.assert_matches_topology(topology)

    retargeted = _topology(_radio("a", endpoint="ip:203.0.113.44"))
    assert retargeted.topology_digest != topology.topology_digest
    with pytest.raises(ValueError, match="retargeted"):
        binding.assert_matches_topology(retargeted)


def test_capture_binding_rejects_serial_forgery_and_epoch_boundary_crossing() -> None:
    assignments = (
        _assignment(0, start=1_000, end=1_500, epoch="epoch-0a"),
        _assignment(0, start=1_500, end=2_000, epoch="epoch-0b"),
        _assignment(1),
    )
    topology = _topology(_radio("a", assignments=assignments))
    with pytest.raises(ValueError, match="ID/serial"):
        CaptureHardwareBindingV1.create(
            session_id="session-a",
            manifest_digest=_DIGEST_B,
            capture_start_utc_ns=1_100,
            capture_end_utc_ns=1_200,
            topology=topology,
            selectors=(
                CapturePathSelectorV1(
                    stream_id="stream-a",
                    radio_id="radio-a",
                    radio_serial="forged-serial",
                    receiver_id=0,
                ),
            ),
        )
    with pytest.raises(ValueError, match="crosses or lacks"):
        CaptureHardwareBindingV1.create(
            session_id="session-a",
            manifest_digest=_DIGEST_B,
            capture_start_utc_ns=1_400,
            capture_end_utc_ns=1_600,
            topology=topology,
            selectors=(
                CapturePathSelectorV1(
                    stream_id="stream-a",
                    radio_id="radio-a",
                    radio_serial="serial-a",
                    receiver_id=0,
                ),
            ),
        )


def test_capture_binding_digest_rejects_path_forgery() -> None:
    document = _binding(_topology(_radio("a"))).model_dump(mode="python")
    document["paths"][0]["physical_receiver_id"] = "forged-physical-path"

    with pytest.raises(ValidationError, match="digest does not match content"):
        CaptureHardwareBindingV1.model_validate(document)


def test_fixture_authority_is_structurally_evidence_only_and_unresolved() -> None:
    authority = FixturePathAuthorityV1.create(
        session_id="trial-132",
        manifest_digest=_DIGEST_A,
        streams=(
            FixtureStreamPathInventoryV1(
                stream_id="radio-1",
                radio_id="fixture-radio-1",
                radio_serial="fixture-serial-1",
                receiver_ids=(0, 1),
            ),
            FixtureStreamPathInventoryV1(
                stream_id="radio-0",
                radio_id="fixture-radio-0",
                radio_serial="fixture-serial-0",
                receiver_ids=(0, 1),
            ),
        ),
    )

    assert tuple(item.stream_id for item in authority.streams) == ("radio-0", "radio-1")
    assert authority.lineage_status == "unresolved"
    assert authority.evidence_only is True
    assert authority.current_analysis_eligible is False
    assert authority.physical_association_permitted is False
    assert authority.calibration_association_permitted is False
    assert authority.promotion_permitted is False
    assert "physical_receiver_id" not in authority.model_dump_json()
    assert "hardware_epoch" not in authority.model_dump_json()


@pytest.mark.parametrize(
    "field",
    [
        "current_analysis_eligible",
        "physical_association_permitted",
        "calibration_association_permitted",
        "promotion_permitted",
    ],
)
def test_fixture_authority_cannot_claim_current_or_association(field: str) -> None:
    authority = FixturePathAuthorityV1.create(
        session_id="trial-132",
        manifest_digest=_DIGEST_A,
        streams=(
            FixtureStreamPathInventoryV1(
                stream_id="radio-0",
                radio_id="fixture-radio-0",
                radio_serial="fixture-serial-0",
                receiver_ids=(0, 1),
            ),
        ),
    )
    document = authority.model_dump(mode="python")
    document[field] = True
    with pytest.raises(ValidationError):
        FixturePathAuthorityV1.model_validate(document)

    document = authority.model_dump(mode="python")
    document["physical_receiver_id"] = "invented-path"
    document["hardware_epoch_external_id"] = "invented-epoch"
    document["calibration_digest"] = _DIGEST_B
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        FixturePathAuthorityV1.model_validate(document)
