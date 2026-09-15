"""Preserve bounded physical revisit evidence, without promoting tracking claims."""

import hashlib, json, shutil
from pathlib import Path

BASE = Path(__file__).parent
root = BASE / "frequency-revisits30-v1"
out = Path(
    "/home/mouse9911/gits/leo-radio20-reboot-publish/reports/figures/2026_09_13_radio20_arm_frequency_revisits"
)
load = lambda p: json.loads(p.read_text())
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
op = load(root / "operator.json")
sequence = load(root / "independent-sequence-review.json")
children = [load(root / f"visit-{n}/independent-visit-review.json") for n in range(3)]
assert op["serial"] == "1040005e0b100007100010000bf33a5d4d" and op["visit_count"] == 3
assert op["before"] == op["after"] and op["temporary_files_removed"] and op["exit_code"] == 0
assert sequence["status"] == "pass" and all(
    c["status"] == "pass" and not c["native_results"] for c in children
)
files = [
    "qualify_frequency_revisits.py",
    "review_frequency_revisit_child.py",
    "review_frequency_revisit_sequence.py",
    "test_frequency_revisit_operator.py",
    "frequency-revisit-admission-tests-v1.xml",
    "frequency-revisit-transition-mutations-v1.json",
    Path(__file__).name,
]
for name in files:
    shutil.copyfile(BASE / name, out / name)
shutil.copyfile(root / "visits.txt", out / "visits30.txt")
result = dict(
    status="pass_bounded_three_visit_plan",
    operator=op,
    sequence=sequence,
    children=children,
    runtime_commit="3db06b7adf5e366b653485d642942585708127df",
    review_commit="ead0397c7",
    native_tracking_qualified=False,
    physical_clean_loss_exercised=False,
    retained_artifact_bytes=sum(r["bytes"] for r in op["artifacts"].values()),
    source_sha256={name: digest(out / name) for name in files},
)
with (out / "physical30-evidence.json").open("x") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
print("evidence_sha256", digest(out / "physical30-evidence.json"))
for c in children:
    print(
        c["rf_seconds"],
        c["grid_values_checked"],
        c["moment_and_dense_fits_checked"],
        c["max_refill_gap_ns"],
    )
