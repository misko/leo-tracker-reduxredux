"""One user-authorized 300s capture, using production ownership and isolated IQ."""

import json
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

from pluto_plus.userspace_iiod import UserspaceIiodDeployment

from leo.acquisition.authority import RadioBusyError
from leo.cli.backend import CliBackendError
from leo.cli.composition import CliSettings, CompositionHooks, LocalAcquisitionBackend
from leo.radio.scanner_iio_compat import endpoint_probe
from leo.scanner.single_rx import SINGLE_RX_PROFILE_ID
from leo.storage.persistent_hop import PersistentHopIqStore

ROOT = Path(__file__).resolve().parents[2]
CANARY_ROOT = Path(sys.argv[2])
OUTPUT = Path(sys.argv[1])
if OUTPUT.exists():
    raise FileExistsError(OUTPUT)


class DiagnosticDeployment(UserspaceIiodDeployment):
    """Retain the owned daemon's bounded log before normal verified cleanup."""

    def __init__(self, configuration):
        self.configuration = configuration
        super().__init__(
            host=configuration.host,
            expected_serial=configuration.expected_serial,
            binary_path=configuration.binary_path,
            known_hosts_path=configuration.known_hosts_path,
            password_path=configuration.password_path,
            serial_probe=endpoint_probe,
        )

    def exit_and_verify(self):
        try:
            if self.active is not None:
                configuration = self.configuration
                result = subprocess.run(
                    [
                        "sshpass",
                        "-f",
                        str(configuration.password_path),
                        "ssh",
                        "-T",
                        "-F",
                        "/dev/null",
                        "-o",
                        "StrictHostKeyChecking=yes",
                        "-o",
                        f"UserKnownHostsFile={configuration.known_hosts_path}",
                        "-o",
                        "GlobalKnownHostsFile=/dev/null",
                        "-o",
                        "PubkeyAuthentication=no",
                        "-o",
                        "PreferredAuthentications=password",
                        "-o",
                        "NumberOfPasswordPrompts=1",
                        f"root@{configuration.host}",
                        f"head -c 65536 {self.active.paths.log}",
                    ],
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
                OUTPUT.with_suffix(".iiod.log").write_bytes(result.stdout)
                print(
                    f"Owned iiOD diagnostic log retained (SSH exit {result.returncode})", flush=True
                )
        except Exception as error:
            print(f"Could not retain iiOD log: {type(error).__name__}: {error}", flush=True)
        finally:
            super().exit_and_verify()


values = {}
for file in (Path("/etc/leo/leo.env"), Path("/etc/leo/acquisition.env")):
    for line in file.read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            values[name] = value.strip().strip('"').strip("'")
for name in tuple(values):
    if (
        name.startswith("LEO_SCANNER_GLRT_")
        or name == "LEO_SCANNER_PERSISTENT_IIOD_BUNDLE_MANIFEST_PATH"
    ):
        del values[name]
values.update(
    LEO_SCANNER_PROFILE=SINGLE_RX_PROFILE_ID,
    LEO_SCANNER_HOP_POLICY="fixed",
    LEO_SCANNER_GLRT_MODE="disabled",
    LEO_SCANNER_PERSISTENT_IIOD_BINARY_PATH=str(ROOT / "runtime/scanner-iiod/iiod"),
    CREDENTIALS_DIRECTORY="/run/credentials/leo-acquisition.service",
)
store = PersistentHopIqStore(CANARY_ROOT)
backend = LocalAcquisitionBackend(
    CliSettings.from_environ(values),
    CompositionHooks(
        persistent_hop_store_factory=lambda _root: store,
        persistent_hop_iiod_lifecycle_factory=DiagnosticDeployment,
    ),
)
slot = datetime.fromtimestamp(int(time.time() // 1200) * 1200, UTC)
intent = backend.scheduled_scanner_intent(
    operation_key=f"scheduled-scanner:{slot:%Y%m%dT%H%M%SZ}",
    scheduled_for=slot,
)
report = dict(
    intent=intent.model_dump(mode="json"), status="starting", started_utc_ns=time.time_ns()
)
print(f"Canary: {intent.configuration.receiver_ids}, 10 MS/s, 300s, isolated writer", flush=True)


def deadline(_signum, _frame):
    raise TimeoutError("bounded qualification exceeded its 15-minute total deadline")


signal.signal(signal.SIGALRM, deadline)
signal.alarm(900)
started = time.monotonic()
try:
    while True:
        try:
            result = backend.capture_scheduled_scanner(intent, cancel=Event())
            break
        except CliBackendError as error:
            if not isinstance(error.__cause__, RadioBusyError) or time.monotonic() - started > 360:
                raise
            print("Existing radio lease active; waiting without starting RF", flush=True)
            time.sleep(10)
    published = store.verify(result.published.session_id)
    receipt = published.manifest.receipt
    report.update(
        status="captured",
        session_id=published.session_id,
        path=str(published.path),
        manifest_sha256=published.manifest_sha256,
        receipt=receipt.model_dump(mode="json"),
        timing=published.manifest.timing.model_dump(mode="json"),
        compressed_bytes=published.manifest.compressed_bytes,
        uncompressed_bytes=published.manifest.uncompressed_bytes,
        queue=published.manifest.queue_telemetry.model_dump(mode="json"),
    )
    assert receipt.qualified and receipt.capture_outcome == "complete"
    assert receipt.valid_duty_ppm >= 900_000 and receipt.continuity_attested
    assert published.manifest.receiver_ids == intent.configuration.receiver_ids
    report["status"] = "capture_passed"
    print(f"Capture passed: {receipt.valid_duty_ppm / 10000:.4f}% valid duty", flush=True)
except BaseException as error:
    report.update(status="failed", error=f"{type(error).__name__}: {error}")
    raise
finally:
    signal.alarm(0)
    report["finished_utc_ns"] = time.time_ns()
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n")
