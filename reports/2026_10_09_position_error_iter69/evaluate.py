"""Ordinary clock proposals then complete-state cross-arm continuation."""

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np
from selection import winner

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter68"))
from audit import make_model  # noqa: E402

sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter52"))
from common_sigma1 import fit, json_value, load_member, read, write_json  # noqa: E402

ARMS = ("fitted-c", "zero-c")


def main(shard):
    plan = read(HERE / "protocol.json")
    assert 0 <= shard < plan["shards"]
    digest = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    for name, expected in plan["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == expected, name
    members = read(REPORTS / "2026_10_08_position_error_iter29/protocol.json")["members"]
    case = load_member(next(m for m in members if m["label"] == "RESERVED-001"))
    census = read(REPORTS / "2026_10_09_position_error_iter53/results.json")
    proposals = read(REPORTS / "2026_10_09_position_error_iter68/results.json")["rows"]
    document = read(REPORTS / "2026_10_08_position_error_iter29/baselines/RESERVED-001.json")
    model = make_model(case, document, 1, census["candidate_union"])

    def attempt(index, order, stage, name, seed, clock, arm):
        path = HERE / "results" / f"{index:03d}-{order:02d}-{arm}.json"
        if path.exists():
            row = read(path)
            assert row["protocol_sha256"] == digest
            assert (row["index"], row["order"], row["stage"], row["name"], row["arm"]) == (
                index,
                order,
                stage,
                name,
                arm,
            )
            return row
        model.initial_clock = np.asarray(clock).copy()
        result = json_value(
            fit(model, np.asarray(seed).copy(), arm=arm, maximum_seconds=20, maximum_iterations=600)
        )
        if arm == "zero-c":
            assert result["vector"][6] == 0
        row = dict(
            index=index,
            region=census["rows"][index]["region"],
            order=order,
            stage=stage,
            name=name,
            arm=arm,
            fit=result,
            protocol_sha256=digest,
        )
        write_json(path, row)
        print(index, stage, name, arm, result["converged"], flush=True)
        return row

    for ordinal, index in enumerate(plan["endpoint_indices"]):
        if ordinal % plan["shards"] != shard:
            continue
        source = census["rows"][index]
        proposal = proposals[index]
        assert source["status"] == proposal["status"] == "feasible"
        assert proposal["index"] == index and proposal["region"] == source["region"]
        np.testing.assert_allclose(
            model.evaluate_joint(np.asarray(source["seed"]), np.asarray(source["clock"]))[0],
            source["common_score"],
            atol=1e-6,
            rtol=0,
        )
        rows = []
        for order, start in enumerate(proposal["starts"]):
            for arm in ARMS:
                rows.append(
                    attempt(
                        index,
                        order,
                        "proposals",
                        start["name"],
                        start["vector"],
                        source["clock"],
                        arm,
                    )
                )
        before = {arm: winner(rows, arm) for arm in ARMS}
        skipped = []
        # Freeze the two pre-continuation winners before fitting either continuation.
        for offset, source_arm in enumerate(ARMS):
            selected = before[source_arm]
            if selected is None:
                skipped.append(
                    dict(source_arm=source_arm, reason="no converged proposal-stage fit")
                )
                continue
            for arm in ARMS:
                rows.append(
                    attempt(
                        index,
                        len(proposal["starts"]) + offset,
                        "continuation",
                        source_arm,
                        selected["fit"]["vector"],
                        selected["fit"]["clock_coefficients"],
                        arm,
                    )
                )
        final = {arm: winner(rows, arm) for arm in ARMS}
        summary = dict(
            index=index,
            region=source["region"],
            protocol_sha256=digest,
            before=before,
            final=final,
            skipped_continuations=skipped,
            attempts=len(rows),
            failures=sum(not r["fit"]["converged"] for r in rows),
        )
        path = HERE / "regions" / f"{index:03d}.json"
        if path.exists():
            assert read(path) == summary
        else:
            write_json(path, summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=int, required=True)
    main(parser.parse_args().shard)
