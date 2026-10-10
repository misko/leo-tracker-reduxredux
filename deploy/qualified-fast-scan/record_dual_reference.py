"""Two explicitly requested 300 s RX-only scans with per-channel LO hypotheses."""

import argparse
import dataclasses
import hashlib
import json
import shutil
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from pluto_plus.radio_lock import acquire_radio_lock
from record_edges import SERIAL, exact_radio_factory

from leo.acquisition.continuous_window_ppu import PpuContinuousWindowSource
from leo.acquisition.starlink_tuning import starlink_edge_rf_center_frequency_hz
from leo.scanner.continuous_recording import run_continuous_recording
from leo.scanner.continuous_window import ContinuousWindowConfiguration
from leo.scanner.short_window import RfMappingAuthority, ShortWindowTarget
from leo.scanner.short_window_recording import json_metadata
from leo.storage.continuous_window import ContinuousWindowWriter

ROOT = Path(__file__).parent / "dual-reference-300s"
DATA = Path("/srv/postgres-nvme/fast8-radio20-dual-reference-20261009")


def frequency_plan(edge):
    result = []
    for ch in range(1, 9):
        lo = 9750000000 if ch <= 4 else 10600000000
        rf = starlink_edge_rf_center_frequency_hz(ch, edge)
        result.append(
            {
                "channel": ch,
                "edge": edge,
                "lnb_lo_hz": lo,
                "nominal_rf_hz": rf,
                "nominal_if_hz": rf - lo,
            }
        )
    assert len({r["nominal_if_hz"] for r in result}) == 8
    return result


def measured_targets(edge):
    radio = exact_radio_factory("ip:192.168.1.20", SERIAL)
    original = None
    targets = []
    readbacks = []
    try:
        radio.open()
        assert radio.identity.serial == SERIAL
        assert radio.read_active_rx_fastlock_profile() is None
        original = radio.read_receiver_settings_readback()
        radio.mute_transmit()
        radio.configure_adaptive_scan_geometry(
            sample_rate_hz=2500000, rf_bandwidth_hz=2000000, manual_gain_db=40, rx_mask=3
        )
        for row in frequency_plan(edge):
            # The exact-write adapter compensates the AD9361 integer readback rounding.
            requested = row["nominal_if_hz"]
            radio.write_center_frequency_bufferless(requested)
            actual = round(radio.read_center_frequency())
            assert actual == requested and radio.read_active_rx_fastlock_profile() is None
            targets.append(
                ShortWindowTarget(
                    f"ch{row['channel']}-{edge}-lo{row['lnb_lo_hz']}",
                    actual,
                    rf_center_hz=actual + row["lnb_lo_hz"],
                    lnb_lo_hz=row["lnb_lo_hz"],
                    channel=row["channel"],
                    edge=edge,
                    rf_mapping_authority=RfMappingAuthority.HYPOTHESIS,
                )
            )
            readbacks.append({**row, "applied_if_hz": actual})
    finally:
        try:
            if original is not None:
                restored = radio.restore_receiver_settings_readback(original)
                (ROOT / f"{edge}-preparation-restoration.json").write_text(
                    json.dumps(json_metadata(dataclasses.asdict(restored)), indent=2) + "\n"
                )
        finally:
            radio.close()
    (ROOT / f"{edge}-tuning-readbacks.json").write_text(json.dumps(readbacks, indent=2) + "\n")
    return tuple(targets)


def emit(value):
    print(json.dumps({"utc": datetime.now(UTC).isoformat(), **value}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    plan = {
        "radio": "192.168.1.20",
        "serial": SERIAL,
        "runs": 2,
        "seconds_per_run": 300,
        "sample_rate_hz": 2500000,
        "analog_bandwidth_hz": 2000000,
        "receivers": ["RX1", "RX2"],
        "window_ms": 20,
        "post_recall_guard_ms": 20,
        "manual_gain_db": 40,
        "transmit": False,
        "physical_lnb_control_changed": False,
        "rf_mapping_authority": "hypothesis",
        "reference_policy": (
            "CH1-4: 9.75 GHz; CH5-8: 10.6 GHz. Physical LNB LO is not switched or attested."
        ),
        "lower": frequency_plan("lower"),
        "upper": frequency_plan("upper"),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return
    for unit in ("leo-v052-adaptive.timer", "leo-v052-adaptive.service"):
        status = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True)
        assert status.stdout.strip() == "inactive", (unit, status.stdout)
    assert shutil.disk_usage("/srv/postgres-nvme").free > 12_000_000_000
    ROOT.mkdir(exist_ok=False)
    DATA.mkdir(exist_ok=False)
    (ROOT / "recording-plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    results = []
    with acquire_radio_lock(SERIAL):
        for edge in ("lower", "upper"):
            config = ContinuousWindowConfiguration(
                targets=measured_targets(edge), gain_db=40, transition_budget_ms=20
            )
            run_id = f"fast8-r20-{edge}-dual-reference-300s"
            folder = DATA / run_id
            folder.mkdir()
            source = PpuContinuousWindowSource(
                "192.168.1.20", expected_serial=SERIAL, radio_factory=exact_radio_factory
            )
            sink = ContinuousWindowWriter(
                folder,
                run_id,
                config,
                radio={
                    "host": "192.168.1.20",
                    "serial": SERIAL,
                    "provider": "ppu-continuous-v5",
                    "physical_lnb_control_changed": False,
                    "reference_policy": plan["reference_policy"],
                },
            )
            counts = Counter()
            quality = Counter()
            last = [0.0]

            def progress(record, counts=counts, quality=quality, last=last, edge=edge, sink=sink):
                if record["state"] == "capture_complete":
                    counts.update(p["decision"] for p in record["powers"])
                    quality.update(record["acquisition"]["quality_flags"])
                    if time.monotonic() - last[0] >= 30:
                        last[0] = time.monotonic()
                        emit(
                            {
                                "edge": edge,
                                "state": "progress",
                                "captured_windows": record["captured_windows"],
                                "durable_windows": sink.durable_windows,
                                "power_decisions": dict(counts),
                                "quality_flags": dict(quality),
                            }
                        )
                elif record["state"] in ("running", "stop_requested"):
                    emit({"edge": edge, **record})

            started = time.monotonic()
            utc = datetime.now(UTC).isoformat()
            result = run_continuous_recording(
                source,
                config,
                sink,
                stop_after_seconds=300,
                on_progress=progress,
                queue_windows=1024,
                queue_bytes=409600000,
                shutdown_timeout_seconds=60,
            )
            document = {
                "edge": edge,
                "path": str(folder),
                "requested_seconds": 300,
                "started_utc": utc,
                "finished_utc": datetime.now(UTC).isoformat(),
                "wall_seconds_including_setup_and_restore": time.monotonic() - started,
                "recording": json_metadata(dataclasses.asdict(result)),
                "power_decisions": dict(counts),
                "quality_flags": dict(quality),
                "reference_policy": plan["reference_policy"],
            }
            (folder / "qualification.json").write_text(json.dumps(document, indent=2) + "\n")
            results.append(document)
            (ROOT / "recording-results.json").write_text(json.dumps(results, indent=2) + "\n")
            emit(
                {
                    "edge": edge,
                    "state": "finished",
                    "windows": result.written_windows,
                    "fault": result.fault,
                }
            )
            assert result.fault is None and result.written_windows == result.captured_windows
            assert result.terminal is not None and result.terminal.state.name == "COMPLETED"
            assert result.terminal.error == 0 and result.restoration.fastlock_inactive
    (ROOT / "complete.json").write_text(
        json.dumps(
            {
                "runs_complete": 2,
                "total_windows": sum(r["recording"]["written_windows"] for r in results),
            }
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
