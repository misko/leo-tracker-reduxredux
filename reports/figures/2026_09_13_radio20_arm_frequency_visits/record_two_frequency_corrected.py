"""Add the corrected live result without rewriting the initial rejection evidence."""

import hashlib
import json
from pathlib import Path
import shutil

BASE = Path(__file__).parent
ROOT = BASE / "two-frequency-visits60-v3"
OUT = Path(
    "/home/mouse9911/gits/leo-radio20-reboot-publish/reports/figures/2026_09_13_radio20_arm_frequency_visits"
)


def read(p):
    return json.loads(p.read_text())


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    result = {
        "scope": "corrected_ARM_two_frequency_transition_qualification",
        "native_tracking_qualified": False,
        "parent_transitions_qualified": True,
        "fw_commit": "fd72f856e2de4c370c3e930f800c7b1c2950a285",
        "initial_evidence_sha256": digest(OUT / "evidence.json"),
        "operator": read(ROOT / "operator.json"),
        "status": read(ROOT / "stdout.json"),
        "sequence": read(ROOT / "independent-sequence-review.json"),
        "mutation_checks": read(BASE / "two-frequency-visits60-v3-mutation-checks.json"),
        "children": [read(ROOT / f"visit-{n}/independent-visit-review.json") for n in range(2)],
    }
    assert result["sequence"]["status"] == "pass" and all(
        c["status"] == "pass" for c in result["children"]
    )
    result["source_files"] = {}
    for name in ("review_two_frequency_sequence_v2.py", "record_two_frequency_corrected.py"):
        shutil.copyfile(BASE / name, OUT / name)
        result["source_files"][name] = digest(OUT / name)
    shutil.copyfile(ROOT / "visits.txt", OUT / "corrected-visits.txt")
    with (OUT / "evidence-corrected.json").open("x") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    print(
        json.dumps(
            {
                "output": str(OUT / "evidence-corrected.json"),
                "sha256": digest(OUT / "evidence-corrected.json"),
                "rf_seconds": sum(c["rf_seconds"] for c in result["children"]),
                "native_results": sum(c["native_results"] for c in result["children"]),
                "accepted_past": sum(c["accepted_past_observations"] for c in result["children"]),
            }
        )
    )


if __name__ == "__main__":
    main()
