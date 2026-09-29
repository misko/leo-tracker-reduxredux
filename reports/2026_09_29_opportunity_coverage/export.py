"""Export public visit and probe metadata; no raw signal reads."""

import inspect
import json
import sys
from pathlib import Path

from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

HERE = Path(__file__).resolve().parent
plan = json.loads((HERE / "plan.json").read_text())
row = next(r for r in plan["records"] if r["dataset"] == sys.argv[1])
store = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
raw = store.load(row["session_id"])
published = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True).inspect(row["session_id"])
assert published.manifest_sha256 == raw.input_manifest_sha256 == row["manifest_sha256"]
visits = [
    dict(
        visit_index=e.visit_index,
        start=e.valid_start_counter,
        end=e.valid_end_counter_exclusive,
        rf_hz=float(e.target.rf_center_hz - e.actual_if_offset_hz),
    )
    for e in published.manifest.receipt.events
]
probes = [
    dict(
        visit_index=p.visit_index,
        receiver=p.receiver_id,
        probe_index=p.probe_index,
        start_ms=p.probe_start_ms,
        valid_start_counter=p.valid_start_counter,
        rf_hz=p.actual_rf_hz,
        candidates=len(p.candidates),
        passing=sum(c.passed_fractional_margin_gate for c in p.candidates),
    )
    for p in raw.probes
]
result = dict(
    **row,
    rate=raw.sample_rate_hz,
    probe_ms=raw.probe_ms,
    qualified=raw.qualified,
    timing_qualified=raw.timing.qualified if raw.timing else False,
    analysis_manifest_sha256=raw.analysis_manifest_sha256,
    visits=visits,
    probes=probes,
)
with (HERE / (row["dataset"] + ".json")).open("x") as f:
    json.dump(result, f, separators=(",", ":"), allow_nan=False)
source = Path(inspect.getfile(ScannerTrackingInputStore))
destination = HERE / "scanner_tracking_source.py.txt"
if not destination.exists():
    with destination.open("xb") as f:
        f.write(source.read_bytes())
print(row["dataset"], len(visits), "visits", len(probes), "receiver probes")
