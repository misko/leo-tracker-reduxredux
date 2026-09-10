"""One bounded scanner application run, with explicit resume/re-pause fencing.

The first queue attempt was cancelled before radio setup. Preserve that failed
operation and its evidence; explicitly retry the same immutable scanner intent
through the public capture application, without editing catalog state.
"""
import json
import logging
import os
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread, Timer

from leo.cli.composition import CliSettings, LocalAcquisitionBackend
from leo.scanner.schedule import canonical_scheduled_scanner_operation_key

logging.basicConfig(level=logging.INFO)
root = Path("/srv/bulk/leo/qualification/scanner-a2731551/attempt-3")
release = Path("/opt/leo-tracker/releases/a27315510de90ceddcb43d43ff40f6f1e26de046")
assert Path(sys.prefix) == release / ".venv"
settings = CliSettings.from_environ()
assert settings.bulk_root == Path("/srv/bulk/leo")
assert settings.scanner_hop_policy == "adaptive"
assert settings.scanner_adaptive_sample_rates_hz == (2_500_000,)
assert settings.scanner_radio_id == "radio_pluto_5d4d"
assert settings.scanner_run_seconds == 300 and settings.scanner_interval_seconds == 1200
assert settings.scanner_dwell_ms == 120
backend = LocalAcquisitionBackend(settings)
now = datetime.now(UTC)
slot = datetime.fromtimestamp(int(now.timestamp() // 1200) * 1200, UTC)
intent = backend.scheduled_scanner_intent(
    operation_key=canonical_scheduled_scanner_operation_key(slot), scheduled_for=slot
)
assert intent.configuration.sample_rate_hz == 2_500_000, "Not a 2.5 MS/s cadence slot"
assert backend.capture_control_snapshot().desired_state == "paused"

def save(name, value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    with (root / name).open("x") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")

save("intent.json", intent)
save("authority-before.json", backend.capture_control_snapshot())
cancel, done = Event(), Event()
for signum in (signal.SIGINT, signal.SIGTERM):
    signal.signal(signum, lambda *_: cancel.set())
timer = Timer(420, cancel.set)
timer.daemon = True
started = time.monotonic()

def heartbeat():
    while not done.wait(30):
        print(json.dumps({"event": "verification_running", "seconds": time.monotonic() - started}), flush=True)

Thread(target=heartbeat, daemon=True).start()
try:
    save("authority-resumed.json", backend.capture_resume(
        operator_id="scanner-main-verification",
        reason="Authorized single 300 s 2.5 MS/s deployed scanner verification; scheduler stopped",
    ))
    timer.start()
    result = backend.capture_scheduled_scanner(intent, cancel=cancel)
    summary = dict(session_id=result.published.session_id,
        manifest_sha256=result.published.manifest_sha256,
        capture_qualified=result.capture_qualified,
        classification_warning=result.classification_warning)
    save("capture-result.json", summary)
    save("public-manifest.json", result.published.manifest)
    print(json.dumps(summary), flush=True)
finally:
    timer.cancel()
    save("authority-after.json", backend.capture_pause(
        operator_id="scanner-main-verification",
        reason="Bounded scanner verification ended; hold pending evidence and UI checks",
        wait=True, timeout_seconds=90,
    ))
    done.set()
    save("wall-time.json", {"elapsed_seconds": time.monotonic() - started})
