"""Conditional northern diagnostic using the two sealed raw detector outputs."""

import argparse
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

from aperture_trial import read, write
from dense_geographic_trial import host
from full_short_run import geographic_projection
from joint_publication import run
from north_combined import HERE, assignments

PINS = {
    "stock": "sha256:1e35f931202a67e122526aaf394192582f46989e3fd89cf9690cb84a4b9b5c17",
    "containing": "sha256:2b4e1282f8205a5c90cef2ab6acb7c666d445592963634e93911160205403427",
}


def rebound(candidate, probe_rows, identity):
    from leo.contracts.digests import canonical_digest

    recipe = canonical_digest(identity)
    digest = canonical_digest(
        [
            "cancellation",
            candidate["source"]["raw_recording_authority_digest"],
            recipe[7:],
            probe_rows,
        ]
    )
    return dict(
        candidate,
        source=dict(candidate["source"], probes=probe_rows, analysis_manifest_sha256=digest),
        provenance=dict(
            candidate["provenance"], detector_sha256=recipe, run_id="blind-compact-" + digest[7:39]
        ),
    )


def intersection(stock, candidate):
    from leo.contracts.digests import canonical_digest

    probe_rows = []
    for original, short in zip(
        stock["source"]["probes"], candidate["source"]["probes"], strict=True
    ):
        if dict(original, candidates=[]) != dict(short, candidates=[]):
            raise ValueError("Counterfactual requires identical signed recording opportunities")
        probe_rows.append(
            dict(short, candidates=short["candidates"] if original["candidates"] else [])
        )
    return rebound(
        candidate,
        probe_rows,
        [
            "diagnostic shared selected lanes v1",
            canonical_digest(stock),
            canonical_digest(candidate),
        ],
    )


def continued(candidate):
    from tools.pipeline_eval.variants import carrier_continuation

    pin = sha256(Path(carrier_continuation.__file__).read_bytes()).hexdigest()
    if pin != "f13fc2e02be5474de37b3efb5fba195e3a45daf534e3fa4e7d60c76500cef9ee":
        raise ValueError("The frozen carrier history filter changed")
    history = carrier_continuation.Continuation()
    projected = []
    for row in candidate["source"]["probes"]:
        _, keep, _ = history.select(row)
        projected.append(dict(row, candidates=[] if keep is None else [row["candidates"][keep]]))
    return rebound(
        candidate,
        projected,
        [
            "causal selective on maximum-margin short factors v1",
            candidate["provenance"]["detector_sha256"],
            pin,
        ],
    )


def replay(case, original_root, root, geo, regional):
    from leo.contracts.digests import canonical_digest

    host()
    pair, _ = assignments()
    paths, packets = {}, {}
    for name, pin in PINS.items():
        if case == "continuation" and name == "stock":
            continue
        (path,) = (original_root / name).glob("fast-scan-automatic-work/*/detections.json")
        native = read(path)
        if canonical_digest(native) != pin:
            raise ValueError("Original measured packet changed")
        paths[name], packets[name] = path, native
    if case in ("intersection", "continuation"):
        packet = (
            continued(packets["containing"])
            if case == "continuation"
            else intersection(packets["stock"], packets["containing"])
        )
        path = root / f"{case}-input.json"
        write(path, packet)
    else:
        path, packet = paths["stock"], packets["stock"]
    subprocess.run(
        [
            sys.executable,
            "-BPs",
            __file__,
            "worker",
            path,
            canonical_digest(packet),
            packet["provenance"]["detector_sha256"][7:],
            root / case,
            pair["recording"],
            pair["archive"]["root"],
            pair["region"],
            geo,
            regional,
        ],
        check=True,
        timeout=90,
    )


def score(root):
    import json

    from joint_publication import artifacts
    from mixture_score import section
    from north_interlaced_raw import NORTH, TRUTH_SHA, verified

    from leo.contracts.digests import canonical_digest

    pair, _ = assignments()
    cases = {}
    for name in ("stock-packet", "intersection", "continuation"):
        path = root / name
        run_info = read(path / "joint-research-receipt.json")
        receipt = run_info["receipt"]
        work = path / "fast-scan-automatic-work"
        terminal = read(work / receipt["run_id"] / "terminal.json")
        (native_path,) = work.glob("*/detections.json")
        native = read(native_path)
        expected = (
            PINS["stock"]
            if name == "stock-packet"
            else canonical_digest(read(root / f"{name}-input.json"))
        )
        images = json.loads(json.dumps(artifacts(path, receipt)))
        if (
            canonical_digest(terminal) != receipt["terminal_sha256"]
            or terminal["native_sha256"] != expected
            or canonical_digest(native) != expected
            or run_info["saved_digest"] != expected
            or receipt["region"] != pair["runs"]["candidate"]["receipt"]["region"]
            or images != run_info["evidence"]
        ):
            raise ValueError(
                "Diagnostic publication must bind the selected inputs, terminal, offer and images"
            )
        cases[name] = dict(
            native=expected,
            terminal=receipt["terminal_sha256"],
            decision=receipt["decision"],
            factors=sum(len(row["candidates"]) for row in native["source"]["probes"]),
            arms=terminal["arms"],
            images=images["images"],
            solve_cpu_s=run_info["solve"]["cpu_s"],
            selected={a: len(rows) for a, rows in run_info["selected_rows"].items()},
        )
    answers = json.loads(verified(HERE.parent / "regional-release/scoring-key.json", TRUTH_SHA))
    (truth,) = {tuple(v["truth"]) for v in answers["answers"].values() if v["recording"] == NORTH}
    for row in cases.values():
        row["score"] = section(row["arms"], truth, pair["runs"]["candidate"]["arms"])
    return dict(original_packets=PINS, cases=cases)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    subs = cli.add_subparsers(dest="mode", required=True)
    worker = subs.add_parser("worker")
    for name in (
        "saved",
        "saved_digest",
        "pin",
        "output",
        "recording",
        "archive",
        "region",
        "geo",
        "regional",
    ):
        worker.add_argument(name, type=str if name in ("saved_digest", "pin") else Path)
    for command, names in (
        ("run", ("original", "root", "geo", "regional")),
        ("score", ("root", "output")),
    ):
        sub = subs.add_parser(command)
        for name in names:
            sub.add_argument(name, type=Path)
        if command == "run":
            sub.add_argument("case", choices=("stock-packet", "intersection", "continuation"))
    options = cli.parse_args()
    if options.mode == "run":
        replay(options.case, options.original, options.root, options.geo, options.regional)
    elif options.mode == "worker":
        options.optimized_full_catalogue = options.verify_images = True
        run(
            options,
            early_regional=True,
            keep_selected_rows=True,
            saved_receiver=options.pin,
            geographic_projector=lambda: geographic_projection(options.geo, options.regional),
            reuse_cold_rows=True,
            reuse_grid_phase_states=True,
        )
    else:
        write(options.output, score(options.root))
