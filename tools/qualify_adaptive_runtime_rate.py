#!/usr/bin/env python3
"""Bounded qualification of native 1.25 MS/s adaptive capture, outside live publication.

Run under the production acquisition flock. No firmware or timer changes are made.
The default is a dry run; --capture explicitly enables one ten-second capture.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import uuid
from pathlib import Path

from run_adaptive_capture_cycle import (
    FREQUENCIES_2P5,
    deterministic_uniform_choice,
    json_value,
)

SERIAL = "1040005e0b100007100010000bf33a5d4d"
URI = "ip:192.168.1.20"


def proposed_rate(serial: str, ordinal: int) -> int:
    """Exactly one of four uniform outcomes selects the lower source rate."""
    choice = deterministic_uniform_choice(serial, ordinal, "rate-1p25-quarter-v1", 4)
    return 1_250_000 if choice == 0 else 2_500_000


def build_setup(rate: int = 1_250_000):
    from pluto_plus.adaptive_scan_campaign import build_adaptive_scan_setup
    from pluto_plus.adaptive_scan_detector import Ci16EnergyDetectorConfig

    setup = build_adaptive_scan_setup(
        session=uuid.uuid4().int & ((1 << 64) - 1) or 1,
        generation=1,
        seed=1,
        source_rate_hz=rate,
        analog_bandwidth_hz=rate,
        duration_ms=10_000,
        dwell_ms=120,
        frequencies_hz=FREQUENCIES_2P5[0::2],
        baseline_weights=(1, 1, 1, 1),
        analysis_digest=Ci16EnergyDetectorConfig(-38.0).analysis_digest,
        transition_budget_ms=20,
        maximum_revisit_ms=3_000,
        rx_mask=3,
        variable_dwell=False,
    )
    setup = dataclasses.replace(setup, protocol_version=2)
    setup.validate()
    return setup


def validate_visit(visit, rate: int = 1_250_000) -> None:
    """Check native sample counters and dual-RX byte geometry, not just setup."""
    from pluto_plus.adaptive_scan import VisitResult

    record = visit.record
    if record.result != VisitResult.COMPLETE:
        raise ValueError("qualification received an incomplete visit")
    if record.source_rate_hz != rate or record.protocol_version != 2:
        raise ValueError("qualification received the wrong source rate or protocol")
    if record.valid_end - record.valid_start != rate * 120 // 1000:
        raise ValueError("qualification visit is not 120 ms at the requested rate")
    if record.iq_bytes != rate * 120 // 1000 * 8 or len(visit.iq) != record.iq_bytes:
        raise ValueError("qualification visit lacks exact dual-RX ci16 data")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--sample-rate", type=int, choices=(1_250_000, 2_500_000), default=1_250_000)
    args = parser.parse_args()
    setup = build_setup(args.sample_rate)
    if not args.capture:
        print(json.dumps(json_value(setup), sort_keys=True))
        return 0

    from pluto_plus.adaptive_scan_archive import AdaptiveScanArchive
    from pluto_plus.adaptive_scan_campaign import run_adaptive_scan_campaign
    from pluto_plus.adaptive_scan_client import AdaptiveScanClient
    from pluto_plus.adaptive_scan_detector import Ci16EnergyDetector, Ci16EnergyDetectorConfig
    from pluto_plus.adaptive_scan_shadow import AdaptiveScanMode

    caps = AdaptiveScanClient("192.168.1.20", timeout_s=5).runtime_capabilities()
    if not (
        caps.protocol_version == 2
        and caps.minimum_rate_hz <= setup.source_rate_hz <= caps.maximum_rate_hz
        and caps.rx_mask & 3 == 3
    ):
        raise RuntimeError("Radio does not advertise native dual-RX runtime-rate support")
    session_id = f"scan-fw-{setup.session:016x}"
    archive = AdaptiveScanArchive(args.output_root, session_id, setup)
    timing = {}

    def retain(visit):
        validate_visit(visit, args.sample_rate)
        archive.append(visit)

    try:
        receipt = run_adaptive_scan_campaign(
            URI, SERIAL, setup, Ci16EnergyDetector(Ci16EnergyDetectorConfig(-38.0)),
            mode=AdaptiveScanMode.ADAPTIVE,
            manual_gain_db=40.0,
            samples_per_block=1_000_000,
            feedback_period_visits=8,
            visit_sink=retain,
            counter_clock_sink=lambda value: timing.update(value.model_dump(mode="json")),
            client_factory=lambda host: AdaptiveScanClient(host, timeout_s=30),
        )
        evidence = json_value(dataclasses.asdict(receipt))
        evidence.update(radio_serial=SERIAL, radio_uri=URI, counter_utc_timing=timing)
        path = archive.finish(receipt.terminal, evidence)
    except BaseException as error:
        # Retain incomplete evidence for diagnosis; never publish it as complete.
        (archive.partial / "qualification-failure.json").write_text(json.dumps({
            "setup": json_value(setup), "error": f"{type(error).__name__}: {error}",
        }, sort_keys=True) + "\n")
        raise
    print(json.dumps({"archive": str(path), "terminal": json_value(receipt.terminal),
                      "preparation": json_value(receipt.preparation.configured),
                      "restoration": json_value(receipt.restoration)}, sort_keys=True))
    if receipt.terminal.error or not receipt.terminal.delivered:
        raise RuntimeError("qualification did not deliver a successful capture")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
