"""Bounded no-RF capability probe of the user's newly selected radio."""

import json
import socket
import xml.etree.ElementTree as ET
from dataclasses import asdict
from pathlib import Path

from pluto_plus.persistent_hop import PERSISTENT_HOP_CAPABILITIES
from pluto_plus.userspace_iiod import UserspaceIiodDeployment

HOST = "192.168.1.17"
SERIAL = "104000bac4950008230026001b440a003a"
OUTPUT = Path("/var/tmp/leo-radio003a-capabilities-20260912-02.json")


def context(port):
    with socket.create_connection((HOST, port), timeout=5) as connection:
        connection.sendall(b"PRINT\n")
        stream = connection.makefile("rb")
        size = int(stream.readline(32))
        if not 0 < size <= 1_000_000:
            raise ValueError("invalid IIO context size")
        root = ET.fromstring(stream.read(size))
    attrs = {
        item.attrib["name"]: item.attrib["value"] for item in root.findall("context-attribute")
    }
    assert attrs["hw_serial"] == SERIAL
    return {
        "attributes": attrs,
        "rx_channels": [
            channel.attrib["id"]
            for device in root.findall("device")
            if device.attrib.get("name") == "cf-ad9361-lpc"
            for channel in device.findall("channel")
            if channel.find("scan-element") is not None
        ],
    }


def port_probe(host, port, timeout):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def serial_probe(host, port, serial, timeout):
    assert host == HOST and serial == SERIAL
    attrs = context(port)["attributes"]
    return attrs.get("iio,buffer-metadata") == "3" and (
        port == 30431 or all(attrs.get(name) == "1" for name in PERSISTENT_HOP_CAPABILITIES)
    )


def main():
    if OUTPUT.exists():
        raise FileExistsError(OUTPUT)
    report = {"serial": SERIAL, "host": HOST, "rf_seconds": 0, "stock": context(30431)}
    deployment = UserspaceIiodDeployment(
        host=HOST,
        expected_serial=SERIAL,
        binary_path=Path("/var/tmp/leo-queued-metadata-builds/candidate-startup/iiod"),
        known_hosts_path=Path("/var/tmp/leo-radio003a-known-hosts-20260912"),
        password_path=Path("/etc/leo/credentials/scanner-iiod-ssh-password"),
        port_probe=port_probe,
        serial_probe=serial_probe,
    )
    try:
        start = deployment.enter_and_attest()
        try:
            report["start"] = asdict(start)
            report["candidate"] = context(30432)
            report["daemon_log"] = deployment.diagnostic_tail()
        finally:
            stop = deployment.exit_and_verify()
            report["stop"] = asdict(stop)
        report["status"] = "capabilities_passed_no_rf"
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        OUTPUT.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
