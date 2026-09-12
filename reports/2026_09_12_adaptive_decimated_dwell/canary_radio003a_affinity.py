"""Single-use, bounded comparison of iiOD's existing R/W CPU affinity option.

The public SSH runner port changes only the exact owned-daemon launch line.
This is a research configuration, not an installed release qualification.
"""

import hashlib
import json
import signal
import socket
import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Timer
from urllib.request import urlopen

from pluto_plus.userspace_iiod import SubprocessSshCommandRunner, UserspaceIiodDeployment

from leo.cli.composition import CliSettings, CompositionHooks, LocalAcquisitionBackend

RELEASE = "caa67df2b6a04d284da15979b75b956071b26e30"
SERIAL = "104000bac4950008230026001b440a003a"
OUTPUT = Path("/var/tmp/leo-radio003a-affinity-20260912.json")
BULK = Path("/srv/bulk/leo-radio003a-affinity-20260912")
REPORT = {"release": RELEASE, "experimental_rw_cpu": 1, "status": "prepared"}


class AffinityRunner:
    def __init__(self):
        self.runner = SubprocessSshCommandRunner()

    def run(self, argv, *, stdin, timeout_s):
        launch = b'nohup "$binary" -u local: -p 30432 >"$log"'
        if stdin is not None and launch in stdin:
            assert stdin.count(launch) == 1
            replacement = stdin.replace(
                launch, b'nohup "$binary" -u local: -p 30432 --rw-cpu-affinity 1 >"$log"'
            )
            REPORT["launch_script_original_sha256"] = hashlib.sha256(stdin).hexdigest()
            REPORT["launch_script_candidate_sha256"] = hashlib.sha256(replacement).hexdigest()
            stdin = replacement
        return self.runner.run(argv, stdin=stdin, timeout_s=timeout_s)


class Lifecycle:
    def __init__(self, configuration):
        assert configuration.host == "192.168.1.17" and configuration.expected_serial == SERIAL
        self.deployment = UserspaceIiodDeployment(
            host=configuration.host,
            expected_serial=configuration.expected_serial,
            binary_path=configuration.binary_path,
            known_hosts_path=configuration.known_hosts_path,
            password_path=configuration.password_path,
            bundle_manifest_path=configuration.bundle_manifest_path,
            runner=AffinityRunner(),
        )

    def enter_and_attest(self):
        self.deployment.enter_and_attest()
        try:
            with socket.create_connection(("192.168.1.17", 30432), timeout=5) as connection:
                connection.sendall(b"PRINT\n")
                stream = connection.makefile("rb")
                size = int(stream.readline(32))
                assert 0 < size < 1_000_000
                root = ET.fromstring(stream.read(size))
            attrs = {x.attrib["name"]: x.attrib["value"] for x in root.findall("context-attribute")}
            assert attrs["hw_serial"] == SERIAL
            assert attrs["iio,iiod-rw-cpu-affinity"] == "1"
            REPORT["attested_rw_cpu"] = 1
        except BaseException:
            self.deployment.exit_and_verify()
            raise

    def diagnostic_tail(self):
        return self.deployment.diagnostic_tail()

    def exit_and_verify(self):
        try:
            REPORT["daemon_log"] = self.diagnostic_tail()
        finally:
            self.deployment.exit_and_verify()


def main():
    if OUTPUT.exists() or BULK.exists():
        raise FileExistsError("preserve previous evidence")
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
        CREDENTIALS_DIRECTORY="/etc/leo/credentials",
    )
    settings = CliSettings.from_environ(values)
    assert settings.scanner_radio_id == "radio_pluto_003a"
    assert settings.acquisition_release_id == RELEASE
    backend = LocalAcquisitionBackend(
        settings, CompositionHooks(persistent_hop_iiod_lifecycle_factory=Lifecycle)
    )
    slot = datetime.fromtimestamp(int(time.time() // 1200) * 1200, UTC)
    intent = backend.scheduled_scanner_intent(
        operation_key=f"scheduled-scanner:{slot:%Y%m%dT%H%M%SZ}", scheduled_for=slot
    )
    REPORT.update(intent=intent.model_dump(mode="json"), maximum_capture_call_seconds=100)
    OUTPUT.write_text(json.dumps(REPORT, indent=2) + "\n")
    cancel = Event()
    timer = Timer(70, cancel.set)

    def deadline(*_):
        cancel.set()
        raise TimeoutError("100-second capture-call deadline")

    signal.signal(signal.SIGALRM, deadline)
    started = time.monotonic()
    REPORT["capture_started_utc_ns"] = time.time_ns()
    timer.start()
    signal.alarm(100)
    try:
        result = backend.capture_scheduled_scanner(intent, cancel=cancel)
        manifest = result.published.manifest
        receipt = manifest.receipt
        REPORT.update(
            session_id=result.published.session_id,
            receipt=receipt.model_dump(mode="json"),
            queue=manifest.queue_telemetry.model_dump(mode="json"),
            timing=manifest.timing.model_dump(mode="json"),
        )
        assert receipt.capture_outcome == "cancelled"
        assert receipt.continuity_attested and receipt.restoration.status == "restored"
        assert "launch_script_candidate_sha256" in REPORT
        REPORT["status"] = "bounded_check_passed"
    except BaseException as error:
        REPORT.update(status="failed", error=str(error), notes=getattr(error, "__notes__", []))
        raise
    finally:
        signal.alarm(0)
        timer.cancel()
        REPORT["charged_rf_upper_bound_seconds"] = time.monotonic() - started
        REPORT["finished_utc_ns"] = time.time_ns()
        OUTPUT.write_text(json.dumps(REPORT, indent=2) + "\n")
        keys = ("status", "session_id", "charged_rf_upper_bound_seconds", "error")
        print(json.dumps({k: REPORT.get(k) for k in keys}))


if __name__ == "__main__":
    main()
