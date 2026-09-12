"""One bounded replacement-radio check through installed production adapters."""

import json
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Timer
from urllib.request import urlopen

from leo.cli.composition import CliSettings, LocalAcquisitionBackend

RELEASE = "caa67df2b6a04d284da15979b75b956071b26e30"
OUTPUT = Path("/var/tmp/leo-radio003a-canary-20260912-03.json")
BULK = Path("/srv/bulk/leo-radio003a-canary-20260912-03")


def main():
    if OUTPUT.exists() or BULK.exists():
        raise FileExistsError("preserve earlier canary evidence")
    with urlopen("http://192.168.1.142:8090/api/v1/acquisition-queue", timeout=10) as stream:
        queue = json.load(stream)
    assert not queue["truncated"] and not any(x["state"] == "leased" for x in queue["items"])
    assert (
        subprocess.run(["systemctl", "is-active", "--quiet", "leo-acquisition.service"]).returncode
        == 3
    )
    values = {}
    for path in (Path("/etc/leo/leo.env"), Path("/etc/leo/acquisition.env")):
        for line in path.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and not line.lstrip().startswith("#"):
                values[key.strip()] = value.strip().strip("'\"")
    values.update(
        LEO_BULK_ROOT=str(BULK),
        LEO_SCANNER_REPORT_ROOT=str(BULK / "scanner-reports"),
        LEO_ACQUISITION_RELEASE_ID=RELEASE,
        LEO_SCANNER_RADIO_ID="radio_pluto_003a",
        LEO_RADIOS_JSON=json.dumps(
            [
                dict(
                    radio_id="radio_pluto_003a",
                    serial="104000bac4950008230026001b440a003a",
                    host="192.168.1.17",
                    receiver_count=2,
                )
            ]
        ),
        LEO_SCANNER_PERSISTENT_IIOD_BINARY_PATH=(
            f"/opt/leo-tracker/releases/{RELEASE}/runtime/scanner-iiod/iiod"
        ),
        CREDENTIALS_DIRECTORY="/etc/leo/credentials",
    )
    values.pop("LEO_SCANNER_PERSISTENT_IIOD_BUNDLE_MANIFEST_PATH", None)
    backend = LocalAcquisitionBackend(CliSettings.from_environ(values))
    slot = datetime.fromtimestamp(int(time.time() // 1200) * 1200, UTC)
    intent = backend.scheduled_scanner_intent(
        operation_key=f"scheduled-scanner:{slot:%Y%m%dT%H%M%SZ}",
        scheduled_for=slot,
    )
    report = dict(
        release=RELEASE,
        intent=intent.model_dump(mode="json"),
        purpose="30-second cancellation/startup check; not 300-second duty qualification",
        status="prepared",
        maximum_capture_call_seconds=90,
    )
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n")
    cancel = Event()
    timer = Timer(30, cancel.set)

    def deadline(*_):
        cancel.set()
        raise TimeoutError("90-second capture-call deadline")

    signal.signal(signal.SIGALRM, deadline)
    started = time.monotonic()
    report["capture_started_utc_ns"] = time.time_ns()
    timer.start()
    signal.alarm(90)
    try:
        result = backend.capture_scheduled_scanner(intent, cancel=cancel)
        manifest = result.published.manifest
        receipt = manifest.receipt
        report.update(
            session_id=result.published.session_id,
            receipt=receipt.model_dump(mode="json"),
            queue=manifest.queue_telemetry.model_dump(mode="json"),
            timing=manifest.timing.model_dump(mode="json"),
        )
        assert receipt.capture_outcome == "cancelled"
        assert receipt.continuity_attested and receipt.restoration.status == "restored"
        report["status"] = "bounded_check_passed"
    except BaseException as error:
        report.update(status="failed", error=str(error), notes=getattr(error, "__notes__", []))
        raise
    finally:
        signal.alarm(0)
        timer.cancel()
        report["charged_rf_upper_bound_seconds"] = time.monotonic() - started
        report["finished_utc_ns"] = time.time_ns()
        OUTPUT.write_text(json.dumps(report, indent=2) + "\n")
        print(
            json.dumps(
                {
                    key: report.get(key)
                    for key in (
                        "status",
                        "session_id",
                        "charged_rf_upper_bound_seconds",
                        "error",
                        "notes",
                    )
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
