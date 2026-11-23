"""Measure the fixed raw northern pair and reuse its detections for both omissions."""

import argparse
import json
import subprocess
from pathlib import Path
from statistics import median
from time import perf_counter

from aperture_trial import RELEASE, archive_identity, read, write
from dense_full_short_raw import checked, usage
from dense_geographic_trial import host
from full_short_physical import environment
from full_short_raw import RECIPE_SHA, SHORT_SHA
from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA
from north_interlaced_raw import (
    BENCH,
    HERE,
    MANIFEST_SHA,
    NORTH,
    OFFER_SHA,
    SOURCE,
    SOURCE_SHA,
    verified,
)
from weak_combined_raw import STOCK, STOCK_PIN

FAR = BENCH / "exact-curved-lookahead-north-offers.json"
FAR_SHA = "283375bbad24eee8a0871a7e878c906fd1471158e7ff070d913f9be8d1267dd7"
CASES = ("containing", "stock", "north-mirror-outside", "north-far")


def assignments():
    pair = json.loads(verified(SOURCE, SOURCE_SHA))
    omissions = json.loads(verified(FAR, FAR_SHA))
    archive = pair["archive"]
    if (
        omissions["archive"] != archive
        or archive_identity(Path(archive["root"])) != archive
        or omissions["specification"] != pair["candidate_specification_digest"]
    ):
        raise ValueError("The northern catalogue or reference build changed")
    recording = Path(pair["recording"])
    verified(recording / "manifest.json", MANIFEST_SHA)
    verified(Path(pair["region"]), OFFER_SHA)
    if (
        recording.name != NORTH
        or subprocess.check_output(
            ["findmnt", "-no", "FSTYPE", "-T", str(recording)], text=True
        ).strip()
        != "tmpfs"
    ):
        raise ValueError("Expected the published tmpfs recording")
    return pair, omissions


def run(root, short, geographic, regional):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification.paired_publication import NAMED_V3, verified_v3

    settings = host()
    pair, omissions = assignments()
    checked(STOCK, STOCK_PIN)
    verified_v3(NAMED_V3)
    for path, pin in (
        (short, SHORT_SHA),
        (geographic, GEOGRAPHIC_SHA),
        (regional, TRACK_SCORES_SHA),
    ):
        checked(path, pin)
    root.mkdir(exist_ok=False)
    env = environment(root)
    python = str(RELEASE / "venv/bin/python")
    subprocess.run(
        [
            python,
            "-Bc",
            "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')",
        ],
        env=env,
        check=True,
        timeout=30,
    )
    shared = ["--recording", pair["recording"], "--archive", pair["archive"]["root"]]
    binary_flags = [
        "--track-graph",
        "installed",
        "--geographic-library",
        geographic,
        "--regional-track-library",
        regional,
        "--reuse-cold-track-rows",
        "--reuse-grid-phase-states",
    ]
    write(
        root / "binding.json",
        dict(
            host=settings,
            cases=CASES,
            archive=pair["archive"],
            input_sha=MANIFEST_SHA,
            short_sha=SHORT_SHA,
            geographic_sha=GEOGRAPHIC_SHA,
            regional_sha=TRACK_SCORES_SHA,
        ),
    )
    packet = digest = None
    for case in CASES:
        directory = root / case
        region = Path(pair["region"])
        if case in omissions["results"]:
            region = root / f"{case}-offer.json"
            write(region, omissions["results"][case]["offer"])
        controls = [*shared, "--region", region]
        if case == "stock":
            directory.mkdir()
            command = [STOCK, *controls, "--bulk-root", directory]
        else:
            inputs = (
                ["--short-binary", short]
                if case == "containing"
                else ["--saved", packet, "--saved-digest", digest]
            )
            command = [
                python,
                "-BPs",
                HERE / "full_short_run.py",
                *controls,
                *inputs,
                *binary_flags,
                "--output",
                directory,
            ]
        with (root / f"{case}-stdout").open("x") as stream:
            before, start = usage(), perf_counter()
            process = subprocess.run(
                command, env=env, stdout=stream, stderr=subprocess.PIPE, text=True, timeout=120
            )
            wall, after = perf_counter() - start, usage()
        clock = dict(
            elapsed_s=wall,
            **{key: val - before[key] for key, val in after.items()},
            status=process.returncode,
        )
        write(root / f"{case}-clock.json", clock)
        if process.returncode:
            raise RuntimeError(process.stderr[-4000:])
        if case == "containing":
            (packet,) = (directory / "fast-scan-automatic-work").glob("*/detections.json")
            digest = canonical_digest(read(packet))


def gates(rows):
    present = rows["containing"]
    deltas = [present["score"]["arms"][arm]["delta_error_km"] for arm in ("c0", "fitted_c")]
    quality = present["decision"] == "complete" and all(
        value is not None and value <= 0.25 for value in deltas
    )
    return dict(
        containing=quality,
        omissions={k: rows[k]["decision"] == "withheld" for k in CASES[2:]},
        elapsed_fraction=present["process"]["elapsed_s"] / rows["stock"]["process"]["elapsed_s"],
    )


def factor_audit(stock, candidate, owner_rows):
    from short_primary_epoch_audit import paired_probes

    pairs = paired_probes(stock, candidate)
    shared, added, lost = {}, {}, set()
    shifts = []
    for key, _, original, selected, _ in pairs:
        if original and selected:
            shared[key] = selected["fractional_margin"]
            shifts.append(
                abs(selected["fractional_tracking_cfo_hz"] - original["fractional_tracking_cfo_hz"])
            )
        elif selected:
            added[key] = selected["fractional_margin"]
        elif original:
            lost.add(key)
    owners = {}
    for arm, rows in owner_rows.items():
        keys = {key for key, _, _ in rows}
        if len(keys) != len(rows) or not keys <= shared.keys() | added.keys():
            raise ValueError("Every assigned row must map to one candidate factor")
        owners[arm] = dict(shared=len(keys & shared.keys()), added=len(keys & added.keys()))
    return dict(
        shared=len(shared),
        candidate_only=len(added),
        stock_only=len(lost),
        candidate_margins={
            "shared_median": median(shared.values()) if shared else None,
            "added_median": median(added.values()) if added else None,
        },
        shared_absolute_cfo_median_hz=median(shifts) if shifts else None,
        shared_cfo_within_250_hz=sum(value <= 250 for value in shifts),
        owners=owners,
    )


def score(root):
    from joint_publication import artifacts
    from mixture_score import section
    from north_interlaced_raw import TRUTH_SHA

    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km

    pair, omissions = assignments()
    controls = pair["runs"]["candidate"]
    clocks = {name: read(root / f"{name}-clock.json") for name in CASES}
    if any(r["status"] for r in clocks.values()):
        raise ValueError("All four processes must complete before scoring")
    answers = json.loads(verified(HERE.parent / "regional-release/scoring-key.json", TRUTH_SHA))
    (truth,) = {tuple(v["truth"]) for v in answers["answers"].values() if v["recording"] == NORTH}
    rows, packets = {}, {}
    for name in CASES:
        directory = root / name
        trial = None if name == "stock" else read(directory / "joint-research-receipt.json")
        receipt = (
            trial["receipt"]
            if trial
            else json.loads((root / "stock-stdout").read_text().splitlines()[-1])
        )
        work = directory / "fast-scan-automatic-work" / receipt["run_id"]
        (packet,) = work.parent.glob("*/detections.json")
        terminal, native = read(work / "terminal.json"), read(packet)
        if name in ("stock", "containing"):
            packets[name] = native
        if name == "containing":
            owner_rows = trial["selected_rows"]
        expected = omissions["results"].get(name, controls)
        region = (
            expected["offer"] if name in omissions["results"] else controls["receipt"]["region"]
        )
        images = artifacts(directory, receipt)
        if (
            receipt["terminal_sha256"] != canonical_digest(terminal)
            or canonical_digest(native) != terminal["native_sha256"]
            or receipt["region"] != Algo08Region.parse(region).document()
            or terminal["region"] != receipt["region"]
            or native["source"]["raw_recording_authority_digest"] != controls["raw_authority"]
            or len(native["source"]["probes"]) != 2400
        ):
            raise ValueError(f"Unbound terminal, native or region for {name}")
        if trial:
            recipe = read(directory / "full-short-recipe.json")
            proj = trial["solve"]["geographic_projector"]
            (proof,) = trial["early_regional"]
            if (
                recipe["graph"] != "installed"
                or not recipe["reuse_cold_track_rows"]
                or not recipe["reuse_grid_phase_states"]
                or recipe["regional_track_sha256"] != TRACK_SCORES_SHA
                or recipe["geographic_sha256"] != GEOGRAPHIC_SHA
                or native["provenance"]["detector_sha256"] != "sha256:" + RECIPE_SHA
                or proj["track_score_native"] != proj["calls"]
                or proj["track_score_fallbacks"]
                or proj["calls"] < proof["result"]["probes_evaluated"]
                or trial["saved_digest"]
                != (None if name == "containing" else rows["containing"]["native_sha256"])
                or (
                    name in omissions["results"]
                    and terminal["native_sha256"] != trial["saved_digest"]
                )
                or json.loads(json.dumps(images)) != trial["evidence"]
            ):
                raise ValueError(
                    f"Changed candidate configuration, signed packet or artifacts for {name}"
                )
        elif any(
            terminal["arms"][a][k] != controls["arms"][a][k]
            for a in controls["arms"]
            for k in ("latlon", "rf_rms_hz")
        ):
            raise ValueError(
                "Fresh installed control differs from archived northern calibration fits"
            )
        grid = None
        if receipt["decision"] == "complete":
            grid = FastStandardAnalysisStore(directory).position_grid(receipt["run_id"])
            if not grid["complete"]:
                raise ValueError(f"Partial diagnostic grid for {name}")
        rows[name] = dict(
            decision=receipt["decision"],
            status=terminal["decision"],
            stock_status=expected.get("status", "ok"),
            clearance_km=face_clearance_km(receipt["region"], truth),
            score=section(terminal["arms"], truth, expected["arms"]),
            process=clocks[name],
            images=images["images"],
            native_sha256=terminal["native_sha256"],
            terminal_sha256=receipt["terminal_sha256"],
            grid_points=grid["evaluated_points"] if grid else 0,
            probes=len(native["source"]["probes"]),
            selections=sum(len(r["candidates"]) for r in native["source"]["probes"]),
            proof=proof["result"] if trial else None,
            projection=proj if trial else None,
            counts=receipt["counts"],
        )
    return dict(
        binding=read(root / "binding.json"),
        cases=rows,
        gates=gates(rows),
        factors=factor_audit(packets["stock"], packets["containing"], owner_rows),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="mode", required=True)
    for name, fields in (
        ("run", ("root", "short", "geographic", "regional")),
        ("score", ("root", "output")),
    ):
        cli = subs.add_parser(name)
        for field in fields:
            cli.add_argument(field, type=Path)
    args = parser.parse_args()
    if args.mode == "run":
        run(args.root, args.short, args.geographic, args.regional)
    else:
        write(args.output, score(args.root))
