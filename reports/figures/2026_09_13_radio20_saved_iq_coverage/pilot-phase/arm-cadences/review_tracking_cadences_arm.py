"""Compare leased ARM cadence runs with independently checked host records."""

import json
from pathlib import Path
import numpy as np
from check_adjacent_c_validity import BASE, digest

# SSH transport emits this exact advisory on the target's existing firmware.
# Preserve it in the receipt; accept no additional benchmark/transport stderr.
SSH_ADVISORY = (
    "** WARNING: connection is not using a post-quantum key exchange algorithm.\r\n"
    '** This session may be vulnerable to "store now, decrypt later" attacks.\r\n'
    "** The server may need to be upgraded. See https://openssh.com/pq.html\r\n"
)


def main():
    output = BASE / "tracking-cadences-arm-v1-results"
    operator = json.loads((output / "operator.json").read_text())
    build = json.loads((BASE / "cadence-arm-build-v1.json").read_text())
    host_review = json.loads((BASE / "cadence-host-review-v1.json").read_text())
    assert (
        host_review["status"] == "pass" and host_review["independently_checked_dense_fits"] == 5545
    )
    assert operator["status"] == "complete_review_pending" and operator["temporary_files_removed"]
    assert operator["serial"] == "1040005e0b100007100010000bf33a5d4d"
    assert operator["before"] == operator["after"]
    observer_build = json.loads((BASE / "observer-cadence-replay-build-v1.json").read_text())
    assert operator["payload_sha256"] == {
        **build["payloads"],
        "observer": observer_build["arm_sha256"],
    }
    assert [(r["cadence"], r["offset"]) for r in operator["cases"]] == [
        (2, 0),
        (2, 1),
        (3, 0),
        (3, 1),
        (3, 2),
    ]
    results = []
    for case in operator["cases"]:
        assert case["exit_code"] == 0 and case["stderr"] in ("", SSH_ADVISORY)
        path = output / case["journal"]
        assert digest(path) == case["sha256"]
        hostpath = BASE / "cadence-host-v1" / case["journal"]
        expected = next(
            r
            for r in build["cases"]
            if r["cadence"] == case["cadence"] and r["offset"] == case["offset"]
        )
        assert digest(hostpath) == expected["journal_sha256"]
        arm = [json.loads(line) for line in path.read_text().splitlines()]
        host = [json.loads(line) for line in hostpath.read_text().splitlines()]
        summary = arm.pop()
        reference = host.pop()
        assert len(arm) == len(host) == summary["measurements"]
        for key in (
            "cadence",
            "offset",
            "accepted",
            "measurements",
            "terminal_frame",
            "prediction_result",
        ):
            assert summary[key] == reference[key]
        assert summary["terminal_frame"] == 1800 and summary["prediction_result"] == 0
        for row, truth in zip(arm, host):
            for key in ("frame", "start", "phase", "step", "rejection"):
                assert row[key] == truth[key]
            for key in ("coherence", "delay_s", "cfo_hz"):
                np.testing.assert_allclose(row[key], truth[key], rtol=2e-10, atol=1e-12)
        timing = np.array([r["elapsed_ns"] for r in arm])
        assert np.all(timing > 0)
        assert sum(timing) == summary["compute_ns"] and max(timing) == summary["maximum_ns"]
        interval = case["cadence"] / 750
        results.append(
            dict(
                cadence=case["cadence"],
                offset=case["offset"],
                measurements=len(arm),
                accepted=summary["accepted"],
                mean_ms=float(timing.mean() / 1e6),
                p99_ms=float(np.quantile(timing, 0.99) / 1e6),
                maximum_ms=float(timing.max() / 1e6),
                over_observation_interval=int(np.count_nonzero(timing > interval * 1e9)),
                compute_to_source_interval_ratio=float(timing.mean() / 1e9 / interval),
            )
        )
    observer_results = []
    assert [r["offset"] for r in operator["observer_cases"]] == [0, 1, 2]
    for case in operator["observer_cases"]:
        assert case["exit_code"] == 0 and case["stderr"] in ("", SSH_ADVISORY)
        path = output / case["journal"]
        assert digest(path) == case["sha256"]
        hostpath = BASE / "observer-cadence-host-v1-results" / f"o{case['offset']}.jsonl"
        arm = [json.loads(line) for line in path.read_text().splitlines()]
        host = [json.loads(line) for line in hostpath.read_text().splitlines()]
        summary = arm.pop()
        reference = host.pop()
        assert len(arm) == len(host) == 200
        for key in ("offset", "accepted", "measurements", "terminal_status"):
            assert summary[key] == reference[key]
        assert summary["terminal_status"] == 0 and summary["elapsed_ns"] > 0
        for row, truth in zip(arm, host):
            for key in ("frame", "start", "phase", "step", "rejection"):
                assert row[key] == truth[key]
            for key in ("coherence", "delay_s", "cfo_hz"):
                np.testing.assert_allclose(row[key], truth[key], rtol=2e-10, atol=1e-12)
        observer_results.append(
            dict(
                offset=case["offset"],
                accepted=summary["accepted"],
                measurements=200,
                total_seconds=summary["elapsed_ns"] / 1e9,
                compute_to_source_interval_ratio=summary["elapsed_ns"] / 1e9 / 0.8,
            )
        )
    result = dict(
        status="pass",
        cases=results,
        observer_cases=observer_results,
        native_tracking_qualified=False,
        receiver_paced=False,
        capture_and_logging_cost_included=False,
        reviewer_sha256=digest(Path(__file__)),
        operator_sha256=digest(output / "operator.json"),
    )
    with (output / "review.json").open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
