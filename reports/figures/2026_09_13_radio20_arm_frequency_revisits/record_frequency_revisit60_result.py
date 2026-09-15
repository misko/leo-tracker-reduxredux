"""Retain verified 60-MS/s revisit and successful frozen-image transition."""

import hashlib, json, shutil, subprocess
from pathlib import Path

BASE = Path(__file__).parent
root = BASE / "frequency-revisits60-v1"
out = Path(
    "/home/mouse9911/gits/leo-radio20-reboot-publish/reports/figures/2026_09_13_radio20_arm_frequency_revisits"
)
load = lambda p: json.loads(p.read_text())
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def privileged(path):
    return subprocess.run(["sudo", "-n", "cat", str(path)], capture_output=True, check=True).stdout


deployment = load_result = json.loads(privileged(BASE / "deploy60-revisits-v1/result.json"))
assert (
    deployment["outcome"] == "success"
    and deployment["returned_firmware"] == "glrt-iq-tracking-r60000000-v1"
)
op = load(root / "operator.json")
sequence = load(root / "independent-sequence-review.json")
children = [load(root / f"visit-{n}/independent-visit-review.json") for n in range(3)]
assert op["serial"] == deployment["returned_serial"] == "1040005e0b100007100010000bf33a5d4d"
assert (
    op["rate"] == 60000000
    and op["before"] == op["after"]
    and op["temporary_files_removed"]
    and op["exit_code"] == 0
)
assert sequence["status"] == "pass" and all(
    c["status"] == "pass" and not c["native_results"] for c in children
)
refusal = load(BASE / "frequency-sweep60-v1/operator.json")
assert refusal["status"] == "admission_refused" and refusal["rf_samples_collected"] == 0
shutil.copyfile(root / "visits.txt", out / "visits60.txt")
shutil.copyfile(Path(__file__), out / Path(__file__).name)
result = dict(
    status="pass_bounded_three_visit_plan",
    deployment_result=deployment,
    deployment_receipt_sha256=hashlib.sha256(
        privileged(Path(deployment["receipt_path"]))
    ).hexdigest(),
    operator=op,
    sequence=sequence,
    children=children,
    four_visit_attempt=refusal,
    native_tracking_qualified=False,
    physical_clean_loss_exercised=False,
    retained_artifact_bytes=sum(r["bytes"] for r in op["artifacts"].values()),
    recorder_sha256=digest(Path(__file__)),
)
with (out / "physical60-evidence.json").open("x") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
print("evidence_sha256", digest(out / "physical60-evidence.json"))
print("identity", op["after"], "bytes", result["retained_artifact_bytes"])
for c in children:
    print(c["rf_seconds"], c["max_refill_gap_ns"])
