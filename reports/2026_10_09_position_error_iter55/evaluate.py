"""Refit every feasible ordinary regional endpoint, without reference scoring."""

import hashlib
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter52"))
from common_sigma1 import (  # noqa: E402
    HARD60_SCORE,
    Hard60Objective,
    InitialClockObjective,
    fit,
    json_value,
    load_member,
    read,
    write_json,
)


def main():
    protocol = read(HERE / "protocol.json")
    digest = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    for name, expected in protocol["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == expected, name
    census = read(REPORTS / "2026_10_09_position_error_iter53/results.json")
    members = read(REPORTS / "2026_10_08_position_error_iter29/protocol.json")["members"]
    case = load_member(next(m for m in members if m["label"] == "RESERVED-001"))
    lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
    bank = case.bank.select([lookup[n] for n in census["candidate_union"]])
    document = read(REPORTS / "2026_10_08_position_error_iter29/baselines/RESERVED-001.json")
    selected = next(
        a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
    )
    cal = document["diagnostics"]["calibrations"][selected["source_basin"]]
    base = Hard60Objective(
        case.prepared.observations,
        bank,
        case.prior,
        replace(HARD60_SCORE, relative_sigma_s=1),
        receiver_baseline_hz=np.asarray(cal["receiver_baseline_hz"]),
    )
    common = InitialClockObjective(
        base, cal["correction"]["nodes_s"], cal["correction"]["knots_hz"], 2
    )
    for index, source in enumerate(census["rows"]):
        for arm in ("fitted-c", "zero-c"):
            path = HERE / "results" / f"{index:03d}-{arm}.json"
            if path.exists():
                saved = read(path)
                assert saved["protocol_sha256"] == digest
                assert (saved["index"], saved["arm"]) == (index, arm)
                continue
            receipt = dict(
                index=index,
                region=source["region"],
                source_arm=source["source_arm"],
                start=source["start"],
                arm=arm,
                protocol_sha256=digest,
                status=source["status"],
                violations=source.get("violations", []),
            )
            if source["status"] == "feasible":
                seed, clock = np.asarray(source["seed"]), np.asarray(source["clock"])
                np.testing.assert_allclose(
                    common.evaluate_joint(seed, clock)[0], source["common_score"], atol=1e-6, rtol=0
                )
                common.initial_clock = clock.copy()
                fitted = json_value(
                    fit(common, seed.copy(), arm=arm, maximum_seconds=20, maximum_iterations=600)
                )
                if arm == "zero-c":
                    assert fitted["vector"][6] == 0
                receipt.update(status="complete", fit=fitted)
            write_json(path, receipt)
            print(
                index,
                source["region"],
                arm,
                receipt["status"],
                receipt.get("fit", {}).get("converged"),
                flush=True,
            )


if __name__ == "__main__":
    main()
