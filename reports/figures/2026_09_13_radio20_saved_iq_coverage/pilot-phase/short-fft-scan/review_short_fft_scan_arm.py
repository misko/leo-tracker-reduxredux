"""Compare every ARM ranking to independently checked host spectra."""

import json, hashlib, sys
from pathlib import Path
import numpy as np

BASE = Path(__file__).parent
root = Path(sys.argv[1])
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
op = json.loads((root / "operator.json").read_text())
manifest = json.loads((BASE / "short-fft-scan-host-v1-results/result.json").read_text())
assert op["status"] == "complete_review_pending" and op["temporary_files_removed"]
assert op["before"] == op["after"]
assert op["serial"] == "1040005e0b100007100010000bf33a5d4d" and op["host"] == "192.168.1.20"
assert (
    op["new_rf_samples"] == op["native_jobs"] == 0 and op["payload_sha256"] == manifest["payloads"]
)
advisory = '** WARNING: connection is not using a post-quantum key exchange algorithm.\r\n** This session may be vulnerable to "store now, decrypt later" attacks.\r\n** The server may need to be upgraded. See https://openssh.com/pq.html\r\n'
assert len(op["cases"]) == 9
assert {(c["fft"], c["repeat"]) for c in op["cases"]} == {
    (n, r) for n in (4096, 8192, 16384) for r in range(3)
}
timings = []
for run in op["cases"]:
    assert run["exit_code"] == 0 and run["stderr"] in ("", advisory)
    path = root / run["journal"]
    assert digest(path) == run["sha256"]
    host = BASE / f"short-fft-scan-host-v1-results/positive-12-fft{run['fft']}.jsonl"
    expected = next(
        c
        for c in manifest["cases"]
        if c["label"] == "positive" and c["number"] == 12 and c["fft"] == run["fft"]
    )
    assert digest(host) == expected["journal_sha256"]
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    prior = [json.loads(line) for line in host.read_text().splitlines()]
    assert len(rows) == len(prior) == 65
    for row, ref in zip(rows[:-1], prior[:-1]):
        assert (row["epoch"], row["frequency"], row["score"]) == (
            ref["epoch"],
            ref["frequency"],
            ref["score"],
        )
        np.testing.assert_allclose(row["rank_power"], ref["rank_power"], rtol=2e-12, atol=2e-14)
    timing = rows[-1]
    assert timing["budget"] == 64 and timing["winner"] == expected["winner"]
    assert timing["total_ns"] == sum(
        timing[k] for k in ("grid_and_legacy_select_ns", "bounded_select_ns", "ranking_ns")
    )
    assert 0 < timing["total_ns"] < 10_000_000_000
    timings.append(dict(fft=run["fft"], **timing))
result = dict(
    status="pass",
    ranked_peaks_verified=576,
    timings=timings,
    new_rf_samples=0,
    live_freshness_qualified=False,
    operator_sha256=digest(root / "operator.json"),
    host_result_sha256=digest(BASE / "short-fft-scan-host-v1-results/result.json"),
    reviewer_sha256=digest(Path(__file__)),
)
with (root / "independent-review.json").open("x") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
print(json.dumps(result, indent=2))
