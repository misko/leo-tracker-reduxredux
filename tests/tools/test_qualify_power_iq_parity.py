from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from tests.scanner.test_power_iq_parity import fixture, mapping
from tools.qualify_power_iq_parity import (
    collect_parity,
    main,
    parity_preparation_frequencies,
    replay,
)


def test_post_open_helper_and_exact_offline_bundle_replay(tmp_path):
    frames, words, _ = fixture()
    events = []

    class Capture:
        def cancel(self):
            raise AssertionError("completed capture must cancel its watchdog")

        def read_block(self):
            index = len(events)
            events.append("IQ")
            frame = frames[min(index, 1)]
            time.sleep(0.005)
            return SimpleNamespace(
                samples=frame.samples[:, :, 0].T.astype(np.complex64)
                + 1j * frame.samples[:, :, 1].T,
                first_sample_sequence=frame.fifo_start,
                stream_id=7,
                buffer_sequence=frame.buffer_sequence,
                missing_samples_before=0,
                overflow_observed=False,
                metadata_flags=1 << 21,
            )

    def helper():
        assert events == ["IQ"]
        return {
            "schema": "leo.power-iq-parity-mmio.v1",
            "session": 1,
            "generation": 2,
            "error": 0,
            "cleanup_error": 0,
            "cleanup_complete": True,
            "record_valid": True,
            "radio_acquired": False,
            "words": words,
            "exit_status": 0,
        }

    result, captured = collect_parity(
        Capture(), helper, mapping=mapping(), session=1, generation=2, adc12_qualified=True
    )
    assert result["passed"] and len(captured) == 2
    payload = b"".join(frame.samples.tobytes() for frame in captured)
    (tmp_path / "capture.ci16").write_bytes(payload)
    result.update(
        mapping=mapping().model_dump(mode="json"),
        adc12_qualified=True,
        capture_sha256=hashlib.sha256(payload).hexdigest(),
        frame_index=[
            dict(
                fifo_start=frame.fifo_start,
                sample_count=len(frame.samples),
                generation=frame.generation,
                buffer_sequence=frame.buffer_sequence,
                missing_samples_before=0,
                overflow=False,
            )
            for frame in captured
        ],
    )
    (tmp_path / "qualification.json").write_text(json.dumps(result))
    assert replay(tmp_path) == result["qualification"]
    for field in ("fault", "close_fault", "radio_close_fault", "restoration_fault"):
        failed = dict(result, **{field: "retained acquisition failure"})
        (tmp_path / "qualification.json").write_text(json.dumps(failed))
        with pytest.raises(ValueError, match="failed parity acquisition"):
            replay(tmp_path)
    for field, value in (
        ("cleanup_error", -5),
        ("record_valid", False),
        ("radio_acquired", True),
        ("schema", "wrong"),
        ("exit_status", 1),
    ):
        failed = dict(result, mmio=dict(result["mmio"], **{field: value}))
        (tmp_path / "qualification.json").write_text(json.dumps(failed))
        with pytest.raises(ValueError, match="MMIO-only"):
            replay(tmp_path)
    (tmp_path / "qualification.json").write_text(json.dumps(result))
    (tmp_path / "capture.ci16").write_bytes(payload[:-1] + bytes([payload[-1] ^ 1]))
    with pytest.raises(ValueError, match="checksum"):
        replay(tmp_path)


def test_mmio_cleanup_failure_cannot_claim_parity():
    frames, words, _ = fixture()
    frame = frames[0]
    capture = SimpleNamespace(
        cancel=lambda: None,
        read_block=lambda: SimpleNamespace(
            samples=frame.samples[:, :, 0].T.astype(np.complex64) + 1j * frame.samples[:, :, 1].T,
            first_sample_sequence=frame.fifo_start,
            stream_id=7,
            buffer_sequence=0,
            missing_samples_before=0,
            overflow_observed=False,
            metadata_flags=1 << 21,
        ),
    )
    result, _ = collect_parity(
        capture,
        lambda: {
            "schema": "leo.power-iq-parity-mmio.v1",
            "session": 1,
            "generation": 2,
            "error": 0,
            "cleanup_error": -5,
            "cleanup_complete": False,
            "record_valid": True,
            "radio_acquired": False,
            "words": words,
            "exit_status": 0,
        },
        mapping=mapping(),
        session=1,
        generation=2,
        adc12_qualified=True,
    )
    assert not result["passed"] and "cleanup" in result["fault"]


def test_direct_collection_interrupts_blocked_public_read_at_deadline():
    cancelled = threading.Event()

    class Capture:
        def read_block(self):
            assert cancelled.wait(1)
            raise RuntimeError("public capture cancelled")

        def cancel(self):
            cancelled.set()

    start = time.monotonic()
    result, frames = collect_parity(
        Capture(),
        lambda: pytest.fail("no IQ admitted"),
        mapping=mapping(),
        session=1,
        generation=2,
        adc12_qualified=False,
        seconds=0.03,
    )
    assert time.monotonic() - start < 0.5 and cancelled.is_set()
    assert not result["passed"] and frames == []


def test_cancelled_capture_drains_helper_before_freezing_response():
    frames, words, _ = fixture()
    cancelled = threading.Event()
    helper_finished = threading.Event()

    class Capture:
        first = True

        def read_block(self):
            if not self.first:
                assert cancelled.wait(1)
                raise RuntimeError("capture cancelled")
            self.first = False
            frame = frames[0]
            return SimpleNamespace(
                samples=frame.samples[:, :, 0].T.astype(np.complex64)
                + 1j * frame.samples[:, :, 1].T,
                first_sample_sequence=frame.fifo_start,
                stream_id=7,
                buffer_sequence=0,
                missing_samples_before=0,
                overflow_observed=False,
                metadata_flags=1 << 21,
            )

        def cancel(self):
            cancelled.set()

    def helper():
        assert cancelled.wait(1)
        time.sleep(0.04)  # MMIO cleanup continues after the IQ deadline.
        helper_finished.set()
        return {
            "schema": "leo.power-iq-parity-mmio.v1",
            "session": 1,
            "generation": 2,
            "exit_status": 0,
            "error": 0,
            "cleanup_error": 0,
            "cleanup_complete": True,
            "record_valid": True,
            "radio_acquired": False,
            "words": words,
        }

    result, _ = collect_parity(
        Capture(),
        helper,
        mapping=mapping(),
        session=1,
        generation=2,
        adc12_qualified=True,
        seconds=0.03,
    )
    assert helper_finished.is_set() and result["control_finished"]
    assert result["mmio"]["cleanup_complete"] and not result["passed"]


def test_native_mmio_controller_fake_registers_and_strict_cpu_build(tmp_path):
    root = Path(__file__).resolve().parents[2]
    executable = tmp_path / "parity-mmio-test"
    subprocess.run(
        [
            "gcc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-O2",
            str(root / "tests/tools/power_iq_parity_test.c"),
            "-o",
            str(executable),
        ],
        check=True,
        capture_output=True,
    )
    result = subprocess.run(
        [str(executable)], check=True, capture_output=True, text=True, timeout=2
    )
    assert "cleanup/wrap passed" in result.stdout


@pytest.mark.parametrize("cleanup_attested", [True, False])
def test_main_prepares_distinct_lo_cache_transitions_and_closes_radio_after_capture_error(
    tmp_path, monkeypatch, cleanup_attested
):
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(mapping().model_dump_json())
    events = []

    @dataclass
    class Settings:
        center_frequency_hz: float

    class Capture:
        def close(self):
            events.append("capture.close")
            raise RuntimeError("close failed")

    class Radio:
        def __init__(self, *args, **kwargs):
            pass

        def configure_rx_layout(self, layout):
            pass

        def open(self):
            events.append("open")

        def read_receiver_settings_readback(self):
            return Settings(1_800_000_000.0)

        def begin_metadata_capture(self, *args, **kwargs):
            return Capture()

        def close(self):
            events.append("radio.close")

    def prepare(uri, serial, setup, **kwargs):
        # Model the public preparation's distinct cached-rate exit requirement.
        assert len(set(setup.frequencies)) == 8
        assert setup.frequencies[0] == 1_800_000_000
        events.append("prepare")
        return SimpleNamespace(configured=Settings(1_870_000_000.0))

    def restore(preparation):
        events.append("restore")
        return Settings(2_400_000_000.0)

    modules = {
        "pluto_plus.adaptive_scan_radio": SimpleNamespace(
            prepare_adaptive_scan_radio=prepare, restore_adaptive_scan_radio=restore
        ),
        "pluto_plus.continuous_scan": SimpleNamespace(
            build_continuous_setup=lambda **kwargs: SimpleNamespace(
                frequencies=kwargs["frequencies_hz"]
            )
        ),
        "pluto_plus.hardware.iio": SimpleNamespace(IioRadioDevice=Radio),
        "pluto_plus.setup_profiles": SimpleNamespace(
            AD9361_2R2T_TARGET_PROFILE=SimpleNamespace(rx_layout_expectation=object())
        ),
        "pluto_plus.standalone_power": SimpleNamespace(
            PowerSshCredentials=lambda *args, **kwargs: SimpleNamespace(known_hosts_sha256=None)
        ),
        "pluto_plus.standalone_power_radio": SimpleNamespace(
            preparation_snapshot=lambda preparation: {"retained_snapshot": True}
        ),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(
        "tools.qualify_power_iq_parity.collect_parity",
        lambda *args, **kwargs: (
            {
                "passed": cleanup_attested,
                "control_finished": True,
                "mmio_started": True,
                "control_cleanup_attested": cleanup_attested,
            },
            [],
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "qualify",
            "--host",
            "fixture",
            "--serial",
            "serial",
            "--if-hz",
            "1800000000",
            "--mapping",
            str(mapping_path),
            "--output-root",
            str(tmp_path),
            "--run-id",
            "run",
        ],
    )
    main()
    assert events == ["prepare", "open", "capture.close", "radio.close"] + (
        ["restore"] if cleanup_attested else []
    )
    saved = json.loads((tmp_path / "run/qualification.json").read_text())
    assert not saved["passed"] and saved["close_fault"] == "close failed"
    if not cleanup_attested:
        assert saved["recovery_required"] and saved["preparation"]["retained_snapshot"]
    assert len(set(parity_preparation_frequencies(6_000_000_000))) == 8
