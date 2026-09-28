"""Bounded RX-only adaptive capture on the selected development radio."""
import argparse
import dataclasses
import enum
import hashlib
import json
import os
from pathlib import Path
import time

from pluto_plus.adaptive_scan_campaign import build_adaptive_scan_setup, run_adaptive_scan_campaign
from pluto_plus.adaptive_scan_detector import Ci16EnergyDetector, Ci16EnergyDetectorConfig
from pluto_plus.adaptive_scan_shadow import AdaptiveScanMode
from pluto_plus.hardware.iio import verify_metadata_runtime


def encode(value):
    if dataclasses.is_dataclass(value):
        return {k: encode(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): encode(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [encode(v) for v in value]
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, enum.Enum):
        return value.value
    return value


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--seconds', type=int, choices=range(5,61), default=45)
    p.add_argument('--rate', type=int, choices=(2500000,10000000), default=2500000)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'runtime.json').write_text(json.dumps(encode(verify_metadata_runtime(3)),indent=2)+'\n')
    detector = Ci16EnergyDetector(Ci16EnergyDetectorConfig(-38.0))
    setup = build_adaptive_scan_setup(session=time.time_ns() & ((1<<63)-1), generation=1,
        seed=1729, source_rate_hz=args.rate, analog_bandwidth_hz=args.rate,
        duration_ms=args.seconds*1000, dwell_ms=120,
        frequencies_hz=(959687498,1209687498,1459687498,1709687500),
        baseline_weights=(1,1,1,1), analysis_digest=detector.config.analysis_digest,
        transition_budget_ms=20, maximum_revisit_ms=3000, rx_mask=3, variable_dwell=False)
    (args.output/'setup.json').write_text(json.dumps(encode(setup),indent=2)+'\n')
    raw_dir=Path('/var/tmp/leo-arm15-concurrent-iq') / os.environ.get('LEO_BENCH_PHASE', args.output.parent.name)
    raw_dir.mkdir(parents=True,exist_ok=False)
    iq_hash=hashlib.sha256(); byte_count=0
    with (raw_dir/'capture.ci16').open('xb') as iq, (args.output/'visits.jsonl').open('x') as visits:
        def sink(visit):
            nonlocal byte_count
            before=time.monotonic_ns(); iq.write(visit.iq); iq_hash.update(visit.iq)
            byte_count+=len(visit.iq)
            visits.write(json.dumps({'host_monotonic_ns':before,'byte_offset':byte_count-len(visit.iq),'record':encode(visit.record),
                'iq_bytes':len(visit.iq),'sink_wall_ms':(time.monotonic_ns()-before)/1e6})+'\n')
            visits.flush()
        def clock_sink(*times):
            (args.output/'start-clock.json').write_text(json.dumps(times)+'\n')
        start=time.monotonic_ns()
        try:
            receipt=run_adaptive_scan_campaign('ip:192.168.1.15','104000b29905000e17000800065934759d',
                setup,detector,mode=AdaptiveScanMode.ADAPTIVE,manual_gain_db=40,
                samples_per_block=1000000,feedback_period_visits=8,visit_sink=sink,
                session_clock_sink=clock_sink)
            (args.output/'receipt.json').write_text(json.dumps(encode(receipt),indent=2)+'\n')
        finally:
            iq.flush(); os.fsync(iq.fileno())
            (args.output/'archive.json').write_text(json.dumps({'path':str(raw_dir/'capture.ci16'),
                'bytes':byte_count,'sha256':iq_hash.hexdigest(),'start_host_ns':start,
                'end_host_ns':time.monotonic_ns()},indent=2)+'\n')


if __name__ == '__main__':
    main()
