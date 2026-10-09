"""Prepare immutable no-fit ambiguity census; executing this freezes but launches nothing."""

import datetime
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    previous = HERE.parent / "2026_10_09_position_error_iter106/protocol.json"
    source = json.loads(previous.read_text())
    hashes = dict(source["source_sha256"])
    for name, expected in hashes.items():
        assert sha(ROOT / name) == expected, name
    hashes[str(previous.relative_to(ROOT))] = sha(previous)
    for path in sorted(HERE.iterdir()):
        if path.is_file() and path.suffix in (".py", ".md"):
            hashes[str(path.relative_to(ROOT))] = sha(path)
    members = source["members"]
    assert len(members) == 148
    labels = [row["member"]["inventory_label"] for row in members]
    assert len(set(labels)) == 148
    counts = {
        name: sum(row["member"]["dataset"] == name for row in members)
        for name in ("DS16", "DS17", "DS18")
    }
    assert counts == dict(DS16=63, DS17=51, DS18=34)
    return dict(
        frozen_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        members=members,
        labels=labels,
        membership_counts=counts,
        source_sha256=hashes,
        optimizer_calls=0,
        rho=0,
        shards=2,
        maximum_workers=2,
        threads_per_worker=1,
        source_policy=(
            "Immutable85 ordinary B7 endpoints via87/106 bindings; "
            "no100Hz/recovered substitution"
        ),
        segmentation=(
            "Shared reference-free prepared bootstrap tracks; unique rows, "
            "sameRX/channel/exactRF,dt(0,2]"
        ),
        parity="Saved/full rho0 score within1e-6; restored prediction gradient within1e-12",
        c_scope="Both archived fitted-c/c0 endpoints; staticc andlast2RFtime c0locks checked",
        reference_scope=(
            "No reference-guided inference; inherited51 archived-error equality "
            "andfullartifactdigest validate provenance"
        ),
        failures=(
            "All148 append-only complete/failed; retainpartialchecks; "
            "no readiness/quality exclusions"
        ),
        scope=(
            "Descriptive consumed-data ambiguity census, "
            "no positive persistence or position optimization"
        ),
    )


def main():
    plan = prepare()
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(plan, stream, indent=2)
        stream.write("\n")
    print("Frozen148 no-fit audit; no recording evaluated")


if __name__ == "__main__":
    main()
