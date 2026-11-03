import pytest
from pydantic import ValidationError

from leo.contracts.power_scanner import StandalonePowerResultV1


def measurement(**changes):
    receivers = [
        dict(
            receiver_id=index,
            energy_sum=0,
            sum_i=0,
            sum_q=0,
            clipping_i=0,
            clipping_q=0,
            adc12_contact_samples=0,
            peak_abs_component=0,
            decision="quiet",
        )
        for index in range(2)
    ]
    fields = dict(
        sequence=0,
        session=1,
        generation=2,
        visit=0,
        sweep=0,
        target_index=0,
        profile=0,
        sample_start=(1 << 32) - 100,
        sample_end_exclusive=(1 << 32) + 49900,
        sample_count=50000,
        flags=0,
        complete=True,
        recall={"profile": 0, "frequency_hz": 1800000000, "profile_crc32": 1},
        table_sha256="sha256:" + "a" * 64,
        guard_samples=50000,
        adc12_qualified=True,
        threshold_energy=(1, 1),
        receivers=receivers,
    )
    return StandalonePowerResultV1(**(fields | changes))


def test_metadata_contract_has_exact_full_counter_and_no_iq_fields():
    value = measurement()
    assert value.counter_identity == "prepack_preincrement_v1"
    assert value.sample_end_exclusive > 1 << 32
    assert value.table_digest_authority == "host_declared"
    assert StandalonePowerResultV1.model_validate_json(value.model_dump_json()) == value
    assert "samples" not in value.model_dump() and "iq_bytes" not in value.model_dump()
    with pytest.raises(ValidationError):
        StandalonePowerResultV1(**(value.model_dump() | {"iq_bytes": 0}))


@pytest.mark.parametrize(
    "changes",
    [
        {"adc12_qualified": False},
        {"sample_count": 100},
        {"flags": 8},
        {"sample_end_exclusive": (1 << 32) + 49901},
    ],
)
def test_unqualified_invalid_geometry_cannot_claim_quiet(changes):
    with pytest.raises(ValidationError):
        measurement(**changes)


def test_clipped_complete_preserves_observation_but_cannot_claim_activity():
    fields = measurement().model_dump()
    fields["receivers"][0]["adc12_contact_samples"] = 1
    with pytest.raises(ValidationError, match="clipped"):
        StandalonePowerResultV1(**fields)
    for receiver in fields["receivers"]:
        receiver["decision"] = "unknown"
    assert StandalonePowerResultV1(**fields).complete
