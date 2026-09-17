"""Run the standalone PPU probe with the deployed, serial-attested iiOD."""
import dataclasses
import json
import runpy
from pathlib import Path

from pluto_plus.userspace_iiod import UserspaceIiodDeployment
from leo.radio.scanner_iio_compat import endpoint_probe

root = Path(__file__).parent
deployment = UserspaceIiodDeployment(
    host="192.168.1.17",
    expected_serial="104000bac4950008230026001b440a003a",
    binary_path=Path("/opt/leo-tracker/releases/af88cba2ec302eae9dfc8553f04e647fde12d7be/runtime/scanner-iiod/iiod"),
    known_hosts_path=Path("/etc/leo/credentials/scanner-iiod-ssh-known-hosts"),
    password_path=Path("/etc/leo/credentials/scanner-iiod-ssh-password"),
    serial_probe=endpoint_probe,
)
start = deployment.enter_and_attest()
(root / "iiod-start.json").write_text(json.dumps(dataclasses.asdict(start), indent=2))
try:
    runpy.run_path(str(root / "probe.py"), run_name="__main__")
finally:
    (root / "iiod-tail.txt").write_text(deployment.diagnostic_tail())
    stop = deployment.exit_and_verify()
    (root / "iiod-stop.json").write_text(json.dumps(dataclasses.asdict(stop), indent=2))
