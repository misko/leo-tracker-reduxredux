"""Retain qualified child results separately from rejected parent evidence."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

BASE = Path(__file__).parent
FW = Path("/home/mouse9911/gits/plutosdr-fw-radio20-tracking")
PUB = Path("/home/mouse9911/gits/leo-radio20-reboot-publish")
OUT = PUB / "reports/figures/2026_09_13_radio20_arm_frequency_visits"


def read(p):
    return json.loads(p.read_text())


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=False)
    result = {
        "scope": "bounded_ARM_frequency_visit_implementation",
        "native_tracking_qualified": False,
        "parent_transitions_qualified": False,
        "serial": "1040005e0b100007100010000bf33a5d4d",
        "address": "192.168.1.20",
        "fw_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=FW, text=True
        ).strip(),
        "radio_run": read(BASE / "two-frequency-visits60-v1/operator.json"),
        "radio_status": read(BASE / "two-frequency-visits60-v1/stdout.json"),
        "parent_association_rejection": read(
            BASE / "two-frequency-visits60-v1-sequence-rejection.json"
        ),
        "corrected_retry": read(BASE / "two-frequency-visits60-v2/operator.json"),
        "children": [
            read(BASE / f"two-frequency-visits60-v1/visit-{n}/independent-visit-review.json")
            for n in range(2)
        ],
        "tests": {},
        "binaries": {},
        "source_files": {},
    }
    assert result["parent_association_rejection"]["status"] == "rejected"
    assert (
        result["corrected_retry"]["status"] == "admission_refused"
        and result["corrected_retry"]["rf_samples_collected"] == 0
    )
    for version in (1, 2):
        junit = BASE / f"two-frequency-visit-tests-v{version}.xml"
        suite = ET.parse(junit).getroot().find("testsuite")
        result["tests"][f"v{version}"] = {
            k: suite.attrib[k] for k in ("tests", "failures", "errors", "skipped", "time")
        }
        shutil.copyfile(junit, OUT / junit.name)
        result["binaries"][f"v{version}"] = digest(BASE / f"glrt-cpu-visit-probe-v{version}")
    for name in (
        "qualify_two_frequency_visits.py",
        "qualify_two_frequency_visits_v2.py",
        "review_two_frequency_visit.py",
        "review_two_frequency_sequence.py",
        "record_two_frequency_results.py",
    ):
        shutil.copyfile(BASE / name, OUT / name)
        result["source_files"][name] = digest(OUT / name)
    shutil.copyfile(BASE / "two-frequency-visits60-v1/visits.txt", OUT / "initial-visits.txt")
    for name in ("glrt_tracking_visit.c", "glrt_tracking_visit.h", "glrt_cpu_visit_probe.c"):
        result["source_files"]["tools/" + name] = digest(FW / "tools" / name)
    result["new_rf_seconds"] = sum(c["rf_seconds"] for c in result["children"])
    result["status"] = "child_arithmetic_pass_parent_evidence_rejected_fix_tested_retry_refused"
    (OUT / "evidence.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(OUT),
                "sha256": digest(OUT / "evidence.json"),
                "bytes": (OUT / "evidence.json").stat().st_size,
                "new_rf_seconds": result["new_rf_seconds"],
            }
        )
    )


if __name__ == "__main__":
    main()
