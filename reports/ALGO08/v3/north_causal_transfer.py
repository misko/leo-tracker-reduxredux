"""Verify the causal receiver from raw northern I/Q and replay both omissions."""

import argparse
import json
from pathlib import Path

from aperture_trial import read, write
from dense_geographic_trial import host
from full_short_south import invoke
from north_combined import CASES, HERE, assignments


def run(reference, saved, root, short, geo, regional):
    from leo.contracts.digests import canonical_digest

    system = host()
    pair, omissions = assignments()
    root.mkdir()
    wanted = canonical_digest(read(saved / "continuation-input.json"))
    flags = [
        "--recording",
        pair["recording"],
        "--archive",
        pair["archive"]["root"],
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
    write(
        root / "binding.json", dict(system=system, archive=pair["archive"], expected_packet=wanted)
    )
    packet = None
    for case in ("containing", *CASES[2:]):
        region = pair["region"]
        if case == "containing":
            inputs = ["--short-binary", short]
        else:
            region = reference / f"{case}-offer.json"
            if read(region) != omissions["results"][case]["offer"]:
                raise ValueError("Changed northern omission")
            inputs = ["--saved", packet, "--saved-digest", wanted]
        output = root / case
        write(
            root / f"{case}-clock.json",
            invoke([*flags, "--region", region, "--output", output, *inputs]),
        )
        (produced,) = output.glob("fast-scan-automatic-work/*/detections.json")
        if canonical_digest(read(produced)) != wanted:
            raise ValueError("Raw or saved causal receiver differs from the frozen signed packet")
        if case == "containing":
            packet = produced


def score(saved, root):
    from joint_publication import artifacts
    from mixture_score import section
    from north_interlaced_raw import NORTH, TRUTH_SHA, verified

    from leo.contracts.digests import canonical_digest

    pair, omissions = assignments()
    measured = read(HERE / "measurements/north-combined.json")["cases"]
    original = read(saved / "continuation/joint-research-receipt.json")
    wanted = read(root / "binding.json")["expected_packet"]
    clocks = {name: read(root / f"{name}-clock.json") for name in ("containing", *CASES[2:])}
    answers = json.loads(verified(HERE.parent / "regional-release/scoring-key.json", TRUTH_SHA))
    (truth,) = {tuple(v["truth"]) for v in answers["answers"].values() if v["recording"] == NORTH}
    rows = {}
    for name, clock in clocks.items():
        directory = root / name
        trial = read(directory / "joint-research-receipt.json")
        receipt = trial["receipt"]
        terminal = read(
            directory / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json"
        )
        evidence = json.loads(json.dumps(artifacts(directory, receipt)))
        expected = omissions["results"].get(name, pair["runs"]["candidate"])
        offer = expected.get("offer", pair["runs"]["candidate"]["receipt"]["region"])
        if (
            canonical_digest(terminal) != receipt["terminal_sha256"]
            or terminal["native_sha256"] != wanted
            or trial["saved_digest"] != (None if name == "containing" else wanted)
            or receipt["region"] != offer
            or terminal["region"] != offer
            or trial["evidence"] != evidence
        ):
            raise ValueError(f"Unbound causal publication for {name}")
        if name == "containing" and (
            evidence["images"] != original["evidence"]["images"]
            or trial["selected_rows"] != original["selected_rows"]
            or receipt["terminal_sha256"] != original["receipt"]["terminal_sha256"]
        ):
            raise ValueError("Raw and saved causal fits differ on the containing offer")
        rows[name] = dict(
            process=clock,
            decision=receipt["decision"],
            terminal=receipt["terminal_sha256"],
            clearance_km=measured[name]["clearance_km"],
            images=evidence["images"],
            score=section(terminal["arms"], truth, expected["arms"]),
            solve_cpu_s=trial["solve"]["cpu_s"],
        )
    ratio = rows["containing"]["process"]["elapsed_s"] / measured["stock"]["process"]["elapsed_s"]
    return dict(
        cases=rows,
        elapsed_fraction=ratio,
        binding=read(root / "binding.json"),
        receiver=read(root / "containing/full-short-recipe.json")["receiver_audit"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="mode", required=True)
    for command, keys in (
        ("run", ("reference", "saved", "root", "short", "geo", "regional")),
        ("score", ("saved", "root", "output")),
    ):
        cli = subs.add_parser(command)
        for key in keys:
            cli.add_argument(key, type=Path)
    args = parser.parse_args()
    if args.mode == "run":
        run(args.reference, args.saved, args.root, args.short, args.geo, args.regional)
    else:
        write(args.output, score(args.saved, args.root))
