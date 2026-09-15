"""Independent dense fits at every retained cadence job; no new RF."""

import json
from pathlib import Path
import numpy as np
from tests.starlink_glrt.test_native_solver import dense_fit
from validate_native_admission import rotated
from check_adjacent_c_validity import BASE, digest


def main():
    build = json.loads((BASE / "cadence-arm-build-v1.json").read_text())
    path = BASE / "paced-original-seed-input-v1/positive.ci16"
    assert digest(path) == build["payloads"]["iq"]
    iq = np.fromfile(path, dtype="<i2").reshape(-1, 2)
    refpath = BASE / "direct-references.ci16"
    assert digest(refpath) == build["payloads"]["refs"]
    refs = np.fromfile(refpath, dtype="<i2").reshape(4, 3300, 4).astype(float)
    bases = []
    for raw in refs:
        pilot = raw[:, 0] + 1j * raw[:, 1]
        bases.append(
            np.column_stack(
                (
                    pilot,
                    -raw[:, 2] - 1j * raw[:, 3],
                    1j * np.pi * 1000 / 2500000 * (2 * np.arange(3300) - 3299) * pilot,
                )
            )
        )
    count = 0
    cases = []
    for case in build["cases"]:
        path = BASE / "cadence-host-v1" / f"c{case['cadence']}-o{case['offset']}.jsonl"
        assert digest(path) == case["journal_sha256"]
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        summary = rows.pop()
        assert len(rows) == summary["measurements"]
        assert summary["accepted"] == sum(r["rejection"] == 0 for r in rows)
        for i, row in enumerate(rows):
            assert row["frame"] == 32 + case["offset"] + i * case["cadence"]
            z = rotated(iq[row["start"] : row["start"] + 3300], 0, row["step"])
            correction, coherence, _ = dense_fit(bases[row["phase"]], z)
            np.testing.assert_allclose(row["coherence"], coherence, rtol=2e-12, atol=2e-14)
            np.testing.assert_allclose(
                row["delay_s"] * 1e6, np.clip(correction[0], -0.25, 0.25), rtol=2e-10, atol=2e-11
            )
            np.testing.assert_allclose(
                row["cfo_hz"],
                row["step"] * 2500000 / 2**32 + np.clip(correction[1], -0.25, 0.25) * 1000,
                rtol=2e-12,
                atol=2e-8,
            )
            assert row["rejection"] == (
                (32 if np.any(abs(correction) >= 0.25) else 0) | (64 if coherence < 0.05 else 0)
            )
            count += 1
        cases.append(summary)
    result = dict(
        status="pass",
        independently_checked_dense_fits=count,
        cases=cases,
        native_tracking_qualified=False,
        arm_cadence_timing_verified=False,
        reviewer_sha256=digest(Path(__file__)),
    )
    with (BASE / "cadence-host-review-v1.json").open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print("PASS", count, "dense fits across", len(cases), "cadence/offset cases")


if __name__ == "__main__":
    main()
