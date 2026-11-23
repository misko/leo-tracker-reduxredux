"""Test two-sided time support on the original signed detector opportunities."""

import argparse
import json
import subprocess
from pathlib import Path
from time import perf_counter, process_time

from aperture_trial import RELEASE, archive_identity, read, write
from causal_short_receiver import FILTER_SHA, identity
from dense_geographic_trial import host
from full_short_graph_transfer import HERE, inputs
from full_short_physical import environment
from full_short_raw import RECIPE_SHA
from local_future_inputs import directions
from north_combined import assignments
from north_factor_swap import PINS, rebound

NORTH = Path("/var/tmp/leo-north-short-regional-nov23/containing")
CASES = ("physical", "north", "south-inside")


def supported(probes):
    forward, backward = directions(probes)
    result = []
    counts = dict(original=0, past_only=0, future_only=0, both=0, neither=0)
    for row, past, future in zip(probes, forward, backward, strict=True):
        if row["candidates"]:
            counts["original"] += 1
            category = (
                ("both" if future else "past_only")
                if past
                else ("future_only" if future else "neither")
            )
            counts[category] += 1
        result.append(row if past or future else dict(row, candidates=[]))
    return result, counts


def select(source):
    identity(RECIPE_SHA)
    if source["provenance"]["detector_sha256"] != "sha256:" + RECIPE_SHA:
        raise ValueError("Unrecognized short receiver")
    projected, counts = supported(source["source"]["probes"])
    identifier = ["short-receiver continuation in either time direction v1", RECIPE_SHA, FILTER_SHA]
    return rebound(source, projected, identifier), counts


def assignment_changes(before, after):
    def owners(rows):
        result = {oid: (sat, role) for oid, sat, role in rows}
        if len(result) != len(rows):
            raise ValueError("Duplicate satellite ownership")
        return result

    first, last = owners(before), owners(after)
    common = first.keys() & last.keys()
    return dict(
        before=len(first),
        after=len(last),
        added=len(last.keys() - first.keys()),
        lost=len(first.keys() - last.keys()),
        changed_satellite=sum(first[key][0] != last[key][0] for key in common),
        changed_role=sum(first[key][1] != last[key][1] for key in common),
    )


def bound(case):
    if case != "north":
        return inputs(case)
    pair, _ = assignments()
    (packet,) = NORTH.glob("fast-scan-automatic-work/*/detections.json")
    return (
        Path(pair["recording"]),
        pair["archive"],
        Path(pair["region"]),
        packet,
        PINS["containing"],
        pair["runs"]["candidate"]["receipt"]["region"],
    )


def replay(case, root, geo, regional):
    from leo.contracts.digests import canonical_digest

    system = host()
    recording, archive, region, original, pin, offer = bound(case)
    source = read(original)
    if canonical_digest(source) != pin or archive_identity(Path(archive["root"])) != archive:
        raise ValueError("Changed original recording or causal archive")
    cpu, start = process_time(), perf_counter()
    packet, counts = select(source)
    selection = dict(cpu_s=process_time() - cpu, elapsed_s=perf_counter() - start)
    saved = root / f"{case}-input.json"
    write(saved, packet)
    digest = canonical_digest(packet)
    command = [
        RELEASE / "venv/bin/python",
        "-BPs",
        HERE / "north_factor_swap.py",
        "worker",
        saved,
        digest,
        packet["provenance"]["detector_sha256"][7:],
        root / case,
        recording,
        archive["root"],
        region,
        geo,
        regional,
    ]
    env = environment(root)
    before = perf_counter()
    subprocess.run(command, check=True, timeout=100, env=env)
    write(
        root / f"{case}-clock.json",
        dict(
            process_elapsed_s=perf_counter() - before,
            selection=selection,
            host=system,
            counts=counts,
            source=pin,
            digest=digest,
            region=offer,
        ),
    )


def score(root):
    from aperture_score import PHYSICAL, references
    from joint_publication import artifacts
    from mixture_score import section

    from leo.contracts.digests import canonical_digest

    transfer = read(HERE / "measurements/causal-selection-transfer.json")
    northern = read(HERE / "measurements/north-combined.json")["cases"]
    (site,) = [
        row["reference"]
        for row in read(PHYSICAL)["cases"]
        if row["dataset_label"] == "DS30-0016" and row["authority_eligible"]
    ]
    refs = references()
    truth = {
        "physical": (site["latitude_deg"], site["longitude_deg"]),
        "north": refs["north-containing"],
        "south-inside": refs["south-containing"],
    }
    clocks = {case: read(root / f"{case}-clock.json") for case in CASES}
    results = {}
    for case, clock in clocks.items():
        _, _, _, original, pin, offer = bound(case)
        packet, counts = select(read(original))
        directory = root / case
        trial = read(directory / "joint-research-receipt.json")
        receipt = trial["receipt"]
        work = directory / "fast-scan-automatic-work"
        (sealed,) = work.glob("*/detections.json")
        terminal = read(work / receipt["run_id"] / "terminal.json")
        images = json.loads(json.dumps(artifacts(directory, receipt)))
        if (
            clock["counts"] != counts
            or clock["source"] != pin
            or canonical_digest(packet) != clock["digest"]
            or read(sealed) != packet
            or clock["digest"] != terminal["native_sha256"]
            or trial["saved_digest"] != clock["digest"]
            or receipt["terminal_sha256"] != canonical_digest(terminal)
            or terminal["region"] != offer
            or receipt["region"] != offer
            or images != trial["evidence"]
        ):
            raise ValueError(f"Unbound published output on {case}")
        baseline = northern["stock"]["score"] if case == "north" else transfer[case]["stock"]
        previous_path = (
            Path("/var/tmp/leo-north-short-causal-raw-nov23/containing")
            if case == "north"
            else Path("/var/tmp/leo-causal-weak-south-nov23") / case
        )
        previous = read(previous_path / "joint-research-receipt.json")
        previous_images = (
            read(HERE / "measurements/north-causal-transfer.json")["cases"]["containing"]["images"]
            if case == "north"
            else transfer[case]["images"]
        )
        if (
            previous["evidence"]["images"] != previous_images
            or previous["receipt"]["region"] != offer
        ):
            raise ValueError("Forward reference differs from its prior published evidence")
        changes = {
            arm: assignment_changes(previous["selected_rows"][arm], rows)
            for arm, rows in trial["selected_rows"].items()
        }
        fit = section(terminal["arms"], truth[case], baseline["arms"])
        results[case] = dict(
            clock=clock,
            decision=receipt["decision"],
            terminal=receipt["terminal_sha256"],
            score=fit,
            stock=baseline,
            images=images["images"],
            solve_cpu_s=trial["solve"]["cpu_s"],
            owners={a: len(v) for a, v in trial["selected_rows"].items()},
            changes_from_forward=changes,
            passes=receipt["decision"] == "complete"
            and all(v["delta_error_km"] <= 0.25 for v in fit["arms"].values()),
        )
    return results


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cmds = cli.add_subparsers(dest="mode", required=True)
    runner = cmds.add_parser("run")
    for key in ("root", "geo", "regional"):
        runner.add_argument(key, type=Path)
    runner.add_argument("case", choices=CASES)
    scorer = cmds.add_parser("score")
    scorer.add_argument("root", type=Path)
    scorer.add_argument("output", type=Path)
    args = cli.parse_args()
    if args.mode == "run":
        replay(args.case, args.root, args.geo, args.regional)
    else:
        write(args.output, score(args.root))
