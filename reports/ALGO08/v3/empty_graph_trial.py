"""Bounded saved comparison on the 13 selected factors from DS30-0227."""

import argparse
from pathlib import Path

from aperture_trial import archive_identity, read, write
from dense_geographic_trial import host
from full_short_south import checked, invoke

from leo.contracts.digests import canonical_digest

PAIR = Path("/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/v3-short-raw-diagnostic-pairs/DS30-0227")
PIN = "6b125f7959da018dd3178a4a663b0c02fa0294a2d85ef921a36767b34cee1352"


def test_pair(root, geo, regional):
    from joint_publication import artifacts

    machine = host()
    pair = checked(PAIR / "result.json", PIN)
    (packet,) = (PAIR / "candidate").glob("fast-scan-automatic-work/*/detections.json")
    digest = canonical_digest(read(packet))
    template = read(PAIR / "candidate/joint-research-receipt.json")
    terminal_pin = template["receipt"]["terminal_sha256"]
    archive = pair["archive"]
    if (
        digest != "sha256:9321bfb1269d3d190403cf21118223c040ef381dfcf22ea78ff5daac901f60f9"
        or archive_identity(Path(archive["root"])) != archive
    ):
        raise ValueError("DS30-0227 binding changed")
    root.mkdir()
    common = [
        "--recording",
        pair["recording"],
        "--archive",
        archive["root"],
        "--region",
        pair["region_file"],
        "--saved",
        packet,
        "--saved-digest",
        digest,
        "--geographic-library",
        geo,
        "--regional-track-library",
        regional,
        "--track-graph",
        "installed",
        "--reuse-cold-track-rows",
        "--reuse-grid-phase-states",
    ]
    runs = {}
    for name, extra in (("skip", ["--skip-empty-proof"]), ("original", [])):
        directory = root / name
        clock = invoke([*common, *extra, "--output", directory])
        report = read(directory / "joint-research-receipt.json")
        receipt = report["receipt"]
        work = directory / "fast-scan-automatic-work" / receipt["run_id"]
        terminal = read(work / "terminal.json")
        (proof,) = report["early_regional"]
        if (
            canonical_digest(terminal) != receipt["terminal_sha256"]
            or terminal_pin != receipt["terminal_sha256"]
            or terminal["native_sha256"] != digest
            or receipt["decision"] != "withheld"
            or terminal["reason"] != "no_active_curvature"
            or report["saved_digest"] != digest
            or bool(proof.get("skipped_empty_graph")) != bool(extra)
            or report["evidence"] != artifacts(directory, receipt)
            or report["evidence"]["images"]
        ):
            raise ValueError(
                "Saved short-recording control or guard differs from the frozen decision"
            )
        runs[name] = dict(clock=clock, proof=proof, solve=report["solve"], receipt=receipt)
    return dict(machine=machine, original_case_sha256=PIN, native=digest, runs=runs)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for arg in ("root", "geo", "regional", "output"):
        cli.add_argument(arg, type=Path)
    args = cli.parse_args()
    write(args.output, test_pair(args.root, args.geo, args.regional))
