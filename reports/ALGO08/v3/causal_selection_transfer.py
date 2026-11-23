"""Transfer the northern causal selection to the saved weak and southern containing packets."""

import argparse
import json
from pathlib import Path

from aperture_trial import archive_identity, read, write
from dense_geographic_trial import host
from full_short_graph_transfer import HERE, inputs
from full_short_south import INSIDE, checked, invoke
from north_factor_swap import continued

CASES = ("physical", "south-inside")


def replay(root, geo, regional):
    from leo.contracts.digests import canonical_digest

    host()
    root.mkdir()
    for name in CASES:
        recording, archive, region, original, pin, _ = inputs(name)
        native = read(original)
        if canonical_digest(native) != pin or archive_identity(Path(archive["root"])) != archive:
            raise ValueError("The development packet or archive changed")
        packet = continued(native)
        saved = root / f"{name}-input.json"
        write(saved, packet)
        flags = [
            "--recording",
            recording,
            "--archive",
            archive["root"],
            "--region",
            region,
            "--output",
            root / name,
            "--saved",
            saved,
            "--saved-digest",
            canonical_digest(packet),
            "--causal-selection",
            "--track-graph",
            "installed",
            "--geographic-library",
            geo,
            "--regional-track-library",
            regional,
            "--reuse-cold-track-rows",
            "--reuse-grid-phase-states",
        ]
        write(root / f"{name}-process.json", invoke(flags))


def score(root):
    from aperture_score import PHYSICAL, references
    from joint_publication import artifacts
    from mixture_score import section

    from leo.contracts.digests import canonical_digest

    prior = read(HERE / "measurements/full-short-graph-transfer.json")
    (row,) = [
        case["reference"]
        for case in read(PHYSICAL)["cases"]
        if case["dataset_label"] == "DS30-0016" and case["authority_eligible"]
    ]
    truth = {
        "physical": [row["latitude_deg"], row["longitude_deg"]],
        "south-inside": references()["south-containing"],
    }
    stock = {
        "physical": read(HERE / "measurements/weak-combined-raw.json")["runs"]["stock"]["arms"],
        "south-inside": checked(
            INSIDE, "48fed3c62639ef81fb99e4b76921bcacd999e769a78ebb607b2b886b6f0951f0"
        )["runs"]["candidate"]["arms"],
    }
    clocks = {name: read(root / f"{name}-process.json") for name in CASES}
    result = {}
    for name in CASES:
        directory = root / name
        data = read(directory / "joint-research-receipt.json")
        receipt = data["receipt"]
        terminal = read(
            directory / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json"
        )
        _, _, _, original, pin, offer = inputs(name)
        packet = read(root / f"{name}-input.json")
        source = read(original)
        if (
            canonical_digest(source) != pin
            or receipt["region"] != offer
            or terminal["region"] != offer
            or canonical_digest(terminal) != receipt["terminal_sha256"]
            or terminal["native_sha256"] != canonical_digest(packet)
            or packet != continued(source)
            or data["saved_digest"] != terminal["native_sha256"]
            or json.loads(json.dumps(artifacts(directory, receipt))) != data["evidence"]
        ):
            raise ValueError("The transfer must reproduce the fixed filter and signed publication")
        before, after = [
            sum(len(row["candidates"]) for row in doc["source"]["probes"])
            for doc in (source, packet)
        ]
        science = section(terminal["arms"], truth[name], stock[name])
        result[name] = dict(
            original_pin=pin,
            after_pin=data["saved_digest"],
            counts=[before, after],
            process=clocks[name],
            images=data["evidence"]["images"],
            decision=receipt["decision"],
            score=science,
            unfiltered=prior[name]["score"],
            stock=section(stock[name], truth[name], stock[name]),
            passes=receipt["decision"] == "complete"
            and all(a["delta_error_km"] <= 0.25 for a in science["arms"].values()),
        )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="mode", required=True)
    for name, keys in (("run", ("root", "geo", "regional")), ("score", ("root", "output"))):
        cli = subs.add_parser(name)
        for key in keys:
            cli.add_argument(key, type=Path)
    args = parser.parse_args()
    if args.mode == "run":
        replay(args.root, args.geo, args.regional)
    else:
        write(args.output, score(args.root))
