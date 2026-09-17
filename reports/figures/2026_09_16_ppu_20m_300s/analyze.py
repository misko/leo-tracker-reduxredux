"""Recompute observed coverage from saved PPU block counters, without IQ."""
import json
from pathlib import Path

root = Path(__file__).parent
report = json.loads((root / "result.json").read_text())
cell = report["cells"][0]
assert cell["complete"] and report["settings_restored"]
assert len(cell["frames"]) == 6000
rate = cell["rate_hz"]
frames = cell["frames"]
assert rate == 20_000_000
origin = frames[0]["first"]
end = origin + 300 * rate
received_first_300 = sum(max(0, min(f["end"], end) - max(f["first"], origin)) for f in frames)
missing = 0
for before, after in zip(frames, frames[1:]):
    gap = after["first"] - before["end"]
    assert gap == after["missing_before"] and gap >= 0
    missing += gap
received = sum(f["end"] - f["first"] for f in frames)
span = frames[-1]["end"] - origin
assert received + missing == span
lengths = sorted(r["samples"] / rate for r in cell["runs"])
gaps = [f["missing_before"] / rate for f in frames[1:] if f["missing_before"]]
summary = {
    "started_utc": report["started_utc"],
    "finished_utc": report["finished_utc"],
    "serial": report["serial"],
    "receiver": 0,
    "sample_rate_hz": rate,
    "received_samples": received,
    "received_iq_seconds": received / rate,
    "source_span_seconds": span / rate,
    "source_coverage_percent": 100 * received / span,
    "first_300_source_seconds_coverage_percent": 100 * received_first_300 / (300 * rate),
    "read_seconds": cell["read_seconds"],
    "payload_MB_per_second": cell["payload_MBps_read"],
    "delivery_equivalent_percent": 100 * cell["delivery_equivalent_duty_read"],
    "missing_samples": missing,
    "gap_count": len(gaps),
    "gap_seconds_min": min(gaps, default=0),
    "gap_seconds_max": max(gaps, default=0),
    "overflow_frames": cell["overflow_frames"],
    "initial_contiguous_seconds": cell["initial_contiguous_seconds"],
    "longest_contiguous_seconds": max(lengths),
    "contiguous_seconds_median": (lengths[(len(lengths)-1)//2] + lengths[len(lengths)//2]) / 2,
    "settings_restored": report["settings_restored"],
    "iq_saved": report["iq_saved"],
}
(root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
