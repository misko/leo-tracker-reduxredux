"""Independent full-resolution checks after reduced-FFT proposal ranking."""

import json
from pathlib import Path

BASE = Path(__file__).parent
reviewer = BASE / "review_missed_candidate_replay.py"
ns = {"__file__": str(reviewer)}
exec(compile(reviewer.read_text().split("\nmanifest=json.loads", 1)[0], str(reviewer), "exec"), ns)
ns["ROOT"] = BASE / "combined-pilot-controls-v1"
root = BASE / "short-fft-scan-host-v1-results"
manifest = json.loads((root / "result.json").read_text())
assert (
    manifest["worker_binary_sha256"]
    == json.loads((BASE / "expanded-worker-v1/result.json").read_text())["binary_sha256"]
)
checks = []
for case in manifest["cases"]:
    label = f"{case['label']}-{case['number']}"
    path = root / f"{label}-fft{case['fft']}-worker.jsonl"
    assert ns["digest"](path) == case["worker_journal_sha256"]
    assert ns["digest"](ns["ROOT"] / label / "iq.ci16") == case["input_sha256"]
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    checks.append(
        dict(fft=case["fft"], **ns["check"](dict(label=label, proposal=case["peak"]), rows))
    )
result = dict(
    status="pass",
    checks=checks,
    result_sha256=ns["digest"](root / "result.json"),
    reviewer_sha256=ns["digest"](Path(__file__)),
    oracle_reviewer_sha256=ns["digest"](reviewer),
)
with (root / "independent-worker-review.json").open("x") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
print(
    dict(
        runs=len(checks),
        hypotheses=sum(c["resolver_hypotheses"] for c in checks),
        fits=sum(c["moment_dense_fits"] for c in checks),
    )
)
