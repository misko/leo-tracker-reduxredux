"""Checkpointed uniform extra-region policy; no truth-guided inference."""

import argparse
import hashlib
import json
import time
from pathlib import Path

# isort: off
from policy import ARMS, endpoint_sources, retry_inventory, winner
from engine import (
    attempt, clock_starts, common_inventory, error_km, inventory, load,
    make_model, read, regional, residuals,
)
# isort: on

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    assert not path.exists(), f"Preserve immutable receipt: {path}"
    path.write_text(json.dumps(value, indent=2) + "\n")


class InvocationComplete(Exception):
    """Bounded invocation stopped between immutable fit attempts."""


def evaluate(binding, digest, deadline):
    member = binding["member"]
    label = member["inventory_label"]
    destination = HERE / "results" / f"{label}.json"
    if destination.exists():
        assert read(destination)["protocol_sha256"] == digest
        return
    previous = read(ROOT / binding["result_source"])["extension"]["operational"]
    common_fields = dict(member=member, protocol_sha256=digest, before=previous,
                         requested_extra_search=binding["requested_extra_search"])
    if not binding["requested_extra_search"]:
        write(destination, dict(common_fields, status="retained", operational=previous))
        return

    def remaining():
        if time.monotonic() >= deadline:
            raise InvocationComplete()

    remaining()
    try:
        case, baseline, _ = load(binding["loader_binding"])
        region_rows = []
        for region in inventory(baseline):
            path = HERE / "regions" / label / f"region-{region['index']:02d}.json"
            if path.exists():
                row = read(path)
                assert row["protocol_sha256"] == digest and row["region"] == region
            else:
                remaining()
                began = time.monotonic()
                try:
                    document, receipt = regional(case, region["point"])
                    document["scope"] = (
                        "Uniform ordinary regional inventory; reference errors evaluation-only"
                    )
                    row = dict(status="complete", document=document, receipt=receipt)
                except Exception as error:
                    row = dict(status="failed", error=repr(error))
                row.update(region=region, protocol_sha256=digest,
                           elapsed_s=time.monotonic() - began)
                write(path, row)
                print(label, "region", region["index"], row["status"], flush=True)
            region_rows.append(row)
        successful = [r for r in region_rows if r["status"] == "complete"]
        census_path = HERE / "census" / f"{label}.json"
        if census_path.exists():
            census = read(census_path)
            assert census["protocol_sha256"] == digest
            model = make_model(case, baseline, 1, census["candidate_union"])
        else:
            remaining()
            model, census = common_inventory(case, baseline, successful)
            census["protocol_sha256"] = digest
            write(census_path, census)

        def run(index, order, stage, name, seed, clock, arm):
            path = HERE / "attempts" / label / f"{index:03d}-{order:02d}-{arm}.json"
            if path.exists():
                row = read(path)
                assert row["protocol_sha256"] == digest
                assert (row["index"], row["order"], row["stage"], row["name"], row["arm"]) == (
                    index, order, stage, name, arm,
                )
                return row
            remaining()
            fitted = attempt(model, seed, clock, arm)
            row = dict(index=index, order=order, stage=stage, name=name, arm=arm,
                       fit=fitted, protocol_sha256=digest)
            write(path, row)
            print(label, index, order, arm, fitted["converged"], flush=True)
            return row

        rows = []
        indices = endpoint_sources(census["rows"])
        for index in indices:
            source = census["rows"][index]
            _, times, values = residuals(model, source["seed"], source["clock"])
            _, starts, _ = clock_starts(source["seed"], times, values)
            current = []
            for order, (name, seed) in enumerate(starts):
                for arm in ARMS:
                    current.append(run(index, order, "proposals", name, seed,
                                       source["clock"], arm))
            before = {arm: winner(current, arm) for arm in ARMS}
            for offset, source_arm in enumerate(ARMS):
                selected = before[source_arm]
                if selected is None:
                    continue
                for arm in ARMS:
                    current.append(run(
                        index, len(starts) + offset, "continuation", source_arm,
                        selected["fit"]["vector"], selected["fit"]["clock_coefficients"], arm,
                    ))
            rows.extend(current)
        selected_retries = retry_inventory(rows)
        # Freeze complete source states before any retry can influence the inventory.
        for order, source in enumerate(selected_retries):
            for arm in ARMS:
                rows.append(run(
                    999, order, "bounded-restart",
                    f"{source['index']}-{source['order']}-{source['arm']}",
                    source["fit"]["vector"], source["fit"]["clock_coefficients"], arm,
                ))
        selected = {arm: winner(rows, arm) for arm in ARMS}
        operational = {}
        for arm in ARMS:
            chosen = selected[arm]
            if chosen is None:
                operational[arm] = previous[arm]
            else:
                operational[arm] = dict(
                    chosen["fit"], stage="common-bank-recovery",
                    error_km=error_km(case.prior, chosen["fit"]["vector"], baseline),
                )
        write(destination, dict(
            common_fields, status="complete", operational=operational, selected=selected,
            fallback_arms=[a for a in ARMS if selected[a] is None],
            region_count=len(region_rows), region_failures=len(region_rows) - len(successful),
            source_indices=indices, candidate_union=census["candidate_union"],
            attempts=len(rows), raw_failed=sum(not r["fit"]["converged"] for r in rows),
        ))
    except InvocationComplete:
        raise
    except Exception as error:
        write(destination, dict(common_fields, status="failed", error=repr(error),
                                operational=previous, fallback_arms=list(ARMS)))


def main(shard):
    plan = read(HERE / "protocol.json")
    assert 0 <= shard < plan["shards"]
    for path, expected in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
    digest = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    deadline = time.monotonic() + 600
    try:
        for ordinal, binding in enumerate(plan["members"]):
            if ordinal % plan["shards"] == shard:
                evaluate(binding, digest, deadline)
    except InvocationComplete:
        print("Bounded invocation complete; resume same shard from immutable receipts", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=int, required=True)
    main(parser.parse_args().shard)
