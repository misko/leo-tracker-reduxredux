"""Compare leased ARM cadence runs with independently checked host records."""

import json
from pathlib import Path
import numpy as np
from check_adjacent_c_validity import BASE, digest


def main():
    output = BASE / "cadence-arm-v2-results"
    operator = json.loads((output / "operator.json").read_text())
    build = json.loads((BASE / "cadence-arm-build-v1.json").read_text())
    host_review = json.loads((BASE / "cadence-host-review-v1.json").read_text())
    assert (
        host_review["status"] == "pass" and host_review["independently_checked_dense_fits"] == 5545
    )
    assert operator["status"] == "complete_review_pending" and operator["temporary_files_removed"]
    assert operator["serial"] == "1040005e0b100007100010000bf33a5d4d"
    assert operator["before"] == operator["after"]
    assert operator["payload_sha256"] == build["payloads"]
    assert [(r["cadence"], r["offset"]) for r in operator["cases"]] == [
        (2, 0),
        (2, 1),
        (3, 0),
        (3, 1),
        (3, 2),
    ]
    results = []
    for case in operator["cases"]:
        assert case["exit_code"] == 0 and case["stderr"] == ""
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
    result = dict(
        status="pass",
        cases=results,
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
