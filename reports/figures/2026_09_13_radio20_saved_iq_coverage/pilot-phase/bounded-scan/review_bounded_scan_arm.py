"""Verify serial, payloads, cleanup, candidate ordering and ARM FFT scores."""

import json, hashlib
from pathlib import Path
import numpy as np

BASE = Path(__file__).parent
root = BASE / "bounded-scan-arm-v1-results"
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
operator = json.loads((root / "operator.json").read_text())
build = json.loads((BASE / "bounded-scan-build-v1.json").read_text())
assert operator["status"] == "complete_review_pending" and operator["temporary_files_removed"]
assert operator["before"] == operator["after"]
assert (
    operator["serial"] == "1040005e0b100007100010000bf33a5d4d"
    and operator["host"] == "192.168.1.20"
)
assert operator["new_rf_samples"] == operator["native_jobs"] == 0
assert operator["payload_sha256"] == build["payloads"]
ranking = json.loads((BASE / "expanded-proposal-ranking-v1.json").read_text())
assert digest(BASE / "expanded-proposal-ranking-v1.json") == build["ranking_sha256"]
case = next(c for c in ranking["cases"] if c["label"] == "positive" and c["number"] == 12)
advisory = '** WARNING: connection is not using a post-quantum key exchange algorithm.\r\n** This session may be vulnerable to "store now, decrypt later" attacks.\r\n** The server may need to be upgraded. See https://openssh.com/pq.html\r\n'
timings = []
assert len(operator["cases"]) == 6
assert {(c["budget"], c["repeat"]) for c in operator["cases"]} == {
    (b, r) for b in (8, 64) for r in range(3)
}
for run in operator["cases"]:
    assert run["exit_code"] == 0 and run["stderr"] in ("", advisory)
    path = root / run["journal"]
    assert digest(path) == run["sha256"]
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    budget = run["budget"]
    assert len(rows) == budget + 1
    for row, expected in zip(rows[:-1], case["scores"]):
        assert (row["epoch"], row["frequency"], row["score"]) == (
            expected["epoch"],
            expected["frequency"],
            expected["coarse_score"],
        )
        np.testing.assert_allclose(row["rank_power"], expected["single"], rtol=2e-12, atol=2e-14)
    timing = rows[-1]
    assert timing["budget"] == budget
    assert (
        timing["winner"]
        == next(b for b in case["budgets"] if b["budget"] == budget)["single_winner"]
    )
    assert timing["total_ns"] == sum(
        timing[k] for k in ("grid_and_legacy_select_ns", "bounded_select_ns", "ranking_ns")
    )
    assert 0 < timing["total_ns"] < 10_000_000_000
    timings.append(timing)
result = dict(
    status="pass",
    ranked_peaks_verified=216,
    operator_sha256=digest(root / "operator.json"),
    reviewer_sha256=digest(Path(__file__)),
    new_rf_samples=0,
    live_freshness_qualified=False,
    timings=timings,
)
with (root / "independent-review.json").open("x") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
print(json.dumps(result, indent=2))
