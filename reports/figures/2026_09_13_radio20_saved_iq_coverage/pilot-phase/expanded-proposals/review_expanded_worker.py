"""Reuse the independent resolver/moment oracle on all expanded winners."""

import json, hashlib, copy
from pathlib import Path

BASE = Path(__file__).parent
reviewer = BASE / "review_missed_candidate_replay.py"
# Load the existing check without executing its old artifact-specific driver.
namespace = {"__file__": str(reviewer)}
exec(
    compile(reviewer.read_text().split("\nmanifest=json.loads", 1)[0], str(reviewer), "exec"),
    namespace,
)
namespace["ROOT"] = BASE / "combined-pilot-controls-v1"
root = BASE / "expanded-worker-v1"
manifest = json.loads((root / "result.json").read_text())
ranking = json.loads((BASE / "expanded-proposal-ranking-v1.json").read_text())
checks = []
mutations = 0
for case, rank in zip(manifest["cases"], ranking["cases"]):
    label = f"{case['label']}-{case['number']}"
    assert namespace["digest"](namespace["ROOT"] / label / "iq.ci16") == case["input_sha256"]
    for index, run in case["runs"].items():
        path = root / f"{label}-{index}.jsonl"
        assert namespace["digest"](path) == run["journal_sha256"]
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        description = dict(label=label, proposal=rank["scores"][int(index) - 1])
        checks.append(dict(winner=int(index), **namespace["check"](description, rows)))
        if case["number"] == 0 and int(index) == min(map(int, case["runs"])):
            for field in ("coherence", "cfo_hz"):
                changed = copy.deepcopy(rows)
                next(r for r in changed if r["kind"] == 3)[field] += 0.001
                try:
                    namespace["check"](description, changed)
                except AssertionError:
                    mutations += 1
                else:
                    raise AssertionError("mutation accepted")
result = dict(
    status="pass",
    cases=checks,
    mutations_rejected=mutations,
    reviewer_sha256=namespace["digest"](Path(__file__)),
    oracle_reviewer_sha256=namespace["digest"](reviewer),
    result_sha256=namespace["digest"](root / "result.json"),
    native_tracking_qualified=False,
)
with (root / "independent-review.json").open("x") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
print(
    json.dumps(
        dict(
            runs=len(checks),
            hypotheses=sum(r["resolver_hypotheses"] for r in checks),
            fits=sum(r["moment_dense_fits"] for r in checks),
            mutations=mutations,
        )
    )
)
