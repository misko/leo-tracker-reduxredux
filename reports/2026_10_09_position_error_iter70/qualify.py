"""Low-concurrency wall-budget qualification on fixed ordinary controls."""

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter68"))
from audit import make_model  # noqa: E402

sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter52"))
from common_sigma1 import fit, json_value, load_member, read, write_json  # noqa: E402


def main(shard):
    plan = read(HERE / "protocol.json")
    assert shard in (0, 1)
    digest = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    for name, expected in plan["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == expected, name
    members = read(REPORTS / "2026_10_08_position_error_iter29/protocol.json")["members"]
    case = load_member(next(m for m in members if m["label"] == "RESERVED-001"))
    census = read(REPORTS / "2026_10_09_position_error_iter53/results.json")
    doc = read(REPORTS / "2026_10_08_position_error_iter29/baselines/RESERVED-001.json")
    model = make_model(case, doc, 1, census["candidate_union"])
    for ordinal, index in enumerate(plan["endpoint_indices"]):
        if ordinal % 2 != shard:
            continue
        source = census["rows"][index]
        for arm in ("fitted-c", "zero-c"):
            path = HERE / "results" / f"{index:03d}-{arm}.json"
            if path.exists():
                assert read(path)["protocol_sha256"] == digest
                continue
            model.initial_clock = np.asarray(source["clock"]).copy()
            result = json_value(
                fit(
                    model,
                    np.asarray(source["seed"]).copy(),
                    arm=arm,
                    maximum_seconds=90,
                    maximum_iterations=600,
                )
            )
            if arm == "zero-c":
                assert result["vector"][6] == 0
            write_json(path, dict(index=index, arm=arm, protocol_sha256=digest, fit=result))
            print(
                index,
                arm,
                result["converged"],
                result["elapsed_s"],
                result["evaluations"],
                flush=True,
            )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--shard", type=int, required=True)
    main(p.parse_args().shard)
