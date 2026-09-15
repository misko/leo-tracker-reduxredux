"""Retain reviewed physical visit results and the implementation correction."""

import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

base = Path(__file__).parent
root = base / "two-frequency-visits30-clean-loss-v1"
out = Path(
    "/home/mouse9911/gits/leo-radio20-reboot-publish/reports/figures/2026_09_13_radio20_clean_loss_visits"
)
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
load = lambda p: json.loads(p.read_text())
children = [load(root / f"visit-{n}/independent-visit-review-v2.json") for n in range(2)]
sequence = load(root / "independent-sequence-review-v2.json")
op = load(root / "operator.json")
assert sequence["status"] == "pass" and all(c["status"] == "pass" for c in children)
assert op["before"] == op["after"] and op["temporary_files_removed"] and op["exit_code"] == 0
xml = base / "two-frequency-loss-review-tests-v3.xml"
suite = ET.parse(xml).getroot().find("testsuite")
assert suite.attrib["tests"] == "217" and all(
    suite.attrib[k] == "0" for k in ("errors", "failures", "skipped")
)
names = [
    "qualify_two_frequency_visits_clean_loss.py",
    "review_two_frequency_loss_visit.py",
    "review_two_frequency_loss_sequence.py",
    "review_native_visit_epochs.py",
    "review_paired_visit_epochs.py",
    "loss-review-regression30-v1.json",
    "two-frequency-loss-review-tests-v1.xml",
    "two-frequency-loss-review-tests-v2.xml",
    "two-frequency-loss-review-tests-v3.xml",
    Path(__file__).name,
]
for name in names:
    shutil.copyfile(base / name, out / name)
shutil.copyfile(root / "visits.txt", out / "visits-v5.txt")
result = dict(
    status="pass_bounded_visits_only",
    firmware_commit="dd422e0996770d564d6b70558d324265ac9fe681",
    operator=op,
    sequence=sequence,
    children=children,
    tests=dict(suite.attrib),
    physical_clean_loss_exercised=False,
    native_tracking_qualified=False,
    superseded_binary_not_deployed="6f8884879c4ee8f9b731fc4687d79b637bcb141cb32e4bb73a5260abd18de149",
    files={name: digest(out / name) for name in names},
    recorder_sha256=digest(Path(__file__)),
)
with (out / "evidence-v5.json").open("x") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
print(digest(out / "evidence-v5.json"))
