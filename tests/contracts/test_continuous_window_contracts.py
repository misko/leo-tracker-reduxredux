from dataclasses import asdict

import pytest
from pydantic import ValidationError

from leo.contracts.continuous_window import ContinuousRunCheckpointV1
from leo.contracts.digests import canonical_digest
from leo.scanner.short_window_recording import json_metadata
from tests.scanner.test_continuous_recording import configuration


def checkpoint(**overrides):
    config = json_metadata(asdict(configuration()))
    fields = dict(
        run_id="run",
        configuration=config,
        configuration_sha256=canonical_digest(config),
        host="fixture",
        serial="serial",
        state="starting",
        updated_utc_ns=0,
    )
    return ContinuousRunCheckpointV1(**(fields | overrides))


def test_checkpoint_configuration_hash_counters_and_retention_are_bound():
    value = checkpoint()
    assert ContinuousRunCheckpointV1.model_validate_json(value.model_dump_json()) == value
    with pytest.raises(ValidationError, match="digest mismatch"):
        checkpoint(configuration_sha256="sha256:" + "0" * 64)
    with pytest.raises(ValidationError, match="counters"):
        checkpoint(captured_windows=1, durable_windows=2)
    with pytest.raises(ValidationError, match="retention"):
        checkpoint(latest_targets={str(index): {} for index in range(9)})
    with pytest.raises(ValidationError):
        ContinuousRunCheckpointV1(**(value.model_dump() | {"duration_ms": 0}))
