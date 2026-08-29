"""Explicitly authorized, bounded operator canary through the real capture port."""

import json
import os
import time
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from threading import Event

import pytest
import yaml

from leo.cli.composition import CliSettings, LocalAcquisitionBackend
from leo.contracts.device_buffer import DDR_RING_EVIDENCE_KEY_V1, DeviceBufferEvidenceV1
from leo.contracts.states import CaptureState
from leo.domain.profiles import load_profile_revision
from leo.storage import RecordingStore


@pytest.mark.hardware
@pytest.mark.postgres
def test_explicit_bounded_ddr_ring_capture(tmp_path: Path) -> None:
    if os.environ.get("LEO_DDR_RING_CANARY_ENABLE") != "1":
        pytest.fail("hardware canary requires explicit LEO_DDR_RING_CANARY_ENABLE=1 authorization")
    radio_id = os.environ["LEO_DDR_RING_CANARY_RADIO_ID"]
    rate = int(os.environ["LEO_DDR_RING_CANARY_RATE_HZ"])
    receiver = int(os.environ["LEO_DDR_RING_CANARY_RX"])
    duration = int(os.environ["LEO_DDR_RING_CANARY_SECONDS"])
    assert rate in (10_000_000, 15_000_000, 20_000_000)
    assert receiver in (0, 1)
    assert duration in (20, 60)
    settings = CliSettings.from_environ()
    assert settings.radio_backend == "pluto"
    assert radio_id in {radio.radio_id for radio in settings.radios}
    source = load_profile_revision(
        settings.profile_root
        / (f"starlink-ch4-lower-{rate // 1_000_000}m-60s-rx{receiver}-ddr-ring-v6.yaml")
    )
    name = f"hardware-ddr-ring-{rate // 1_000_000}m-{duration}s-rx{receiver}-v1"
    profile = source.profile.model_copy(
        update={
            "name": name,
            "duration_seconds": Decimal(duration),
        }
    )
    profile_root = tmp_path / "profiles"
    profile_root.mkdir()
    (profile_root / f"{name}.yaml").write_text(
        yaml.safe_dump(profile.model_dump(mode="json")), encoding="utf-8"
    )
    backend = LocalAcquisitionBackend(replace(settings, profile_root=profile_root))
    session_id = f"ddr-ring-{time.time_ns()}-{radio_id.rsplit('_', 1)[-1]}-{rate // 1_000_000}m"
    started = time.monotonic()
    result = backend.capture_once(
        profile_name=name,
        radio_ids=(radio_id,),
        session_id=session_id,
        cancel=Event(),
        extra_tags=("DDR_RING_CANARY",),
    )
    print(result.model_dump_json())
    assert result.state in (CaptureState.COMMITTED, CaptureState.DEGRADED)
    store = RecordingStore.open_read_only(settings.bulk_root)
    bundle = store.inspect(session_id)
    verification = store.verify(bundle)
    stream = bundle.manifest.streams[0]
    reader = store.reader(bundle, stream.stream_id)
    evidence = DeviceBufferEvidenceV1.model_validate(
        next(reader.iter_timeline_metadata()).hardware_metadata[DDR_RING_EVIDENCE_KEY_V1]
    )
    assert evidence.request.requested_bytes == evidence.protected_prefix_bytes == 200_000_000
    assert evidence.returned_frames == rate * duration // 1_000_000
    assert stream.logical_sample_count == rate * duration
    assert stream.continuity.enqueue_failure_count == 0
    assert stream.observed_sample_count + stream.zero_fill_sample_count == rate * duration
    print(
        json.dumps(
            {
                "session_id": session_id,
                "manifest": str(bundle.path / "manifest.json"),
                "elapsed_seconds": time.monotonic() - started,
                "verified_chunks": verification.chunk_count,
                "observed_fraction": stream.observed_sample_count / stream.logical_sample_count,
                "queue_high_water": stream.continuity.queue_high_water_refills,
                "evidence": evidence.model_dump(mode="json"),
            },
            sort_keys=True,
        )
    )
