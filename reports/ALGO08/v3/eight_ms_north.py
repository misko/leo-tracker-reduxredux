"""Transfer the paired aperture test to the original public North containing case."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from aperture_trial import ARMS, RELEASE, read, write
from dense_full_short_raw import checked
from dense_geographic_trial import host
from full_short_physical import environment
from full_short_run import EIGHT_MS_SHA, GEOGRAPHIC_SHA, SHORT_SHA, TRACK_SCORES_SHA
from north_combined import assignments
from north_interlaced_raw import NORTH, TRUTH_SHA
from weak_combined_raw import HERE, measure


ORDER = ("12ms", "8ms")
ORIGINAL = Path("/var/tmp/leo-north-short-regional-nov23/containing")
ORIGINAL_SHA = "3d8beaf10a6d3e9c4025627fec4a8a0f864f78e6fd4d6c6061573b1a4b7f2f13"
REFERENCE_SHA = "871105154ab79679308cf7455ee10c236094d8735a02c17ed11bb2412283172e"


def authorized(physical):
    from eight_ms_physical_score import REFERENCE_SHA as WEAK_REFERENCE, quality

    saved = physical.read_bytes()
    row = json.loads(saved)
    runs = row["runs"]
    recomputed = quality(runs["8ms"]["errors_km"], {name: runs[name]["errors_km"] for name in ("12ms", "v3")},
                         complete=runs["8ms"]["decision"] == "complete")
    if (row["case"] != "DS30-0016" or row["original_pair_sha256"] != WEAK_REFERENCE
            or row["position"] != recomputed or not recomputed["passes"]):
        raise ValueError("The frozen physical position gate did not authorize public transfer")
    return sha256(saved).hexdigest()


def run(root, physical, short, eight, geographic, regional):
    from leo.storage.fast_scan import FastScanStore

    system = host()
    authorization = authorized(physical)
    pair, _ = assignments()
    for path, pin in ((short, SHORT_SHA), (eight, EIGHT_MS_SHA), (geographic, GEOGRAPHIC_SHA), (regional, TRACK_SCORES_SHA)):
        checked(path, pin)
    root.mkdir()
    env = environment(root)
    python = str(RELEASE / "venv/bin/python")
    session, inventory, source = FastScanStore(root).inventory(Path(pair["recording"]), verify_windows=False)
    stock = pair["runs"]["candidate"]
    if session != stock["receipt"]["session_id"] or source["window_count"] != 1200:
        raise ValueError("Public recording differs from the original signed containing case")
    request = dict(recording=pair["recording"], archive=pair["archive"], region_file=pair["region"],
                   offered_region=stock["receipt"]["region"], raw_authority=stock["raw_authority"], session=session)
    shared = [python, "-BPs", str(HERE / "full_short_run.py"), "--recording", pair["recording"],
              "--archive", pair["archive"]["root"], "--region", pair["region"], "--track-graph", "installed",
              "--geographic-library", str(geographic), "--regional-track-library", str(regional),
              "--reuse-cold-track-rows", "--reuse-grid-phase-states"]
    commands = {"12ms": [*shared, "--short-binary", str(short), "--output", str(root / "12ms")],
                "8ms": [*shared, "--short-binary", str(eight), "--eight-ms-primary", "--output", str(root / "8ms")]}
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    write(root / "binding.json", dict(machine=system, request=request, inventory=inventory,
                                     physical_score_sha256=authorization, order=ORDER, commands=commands))
    for arm in ORDER:
        measure(commands[arm], env, root, arm)


def score(root, physical):
    from eight_ms_physical_score import comparison, quality, read_run
    from tools.pipeline_eval.qualification.paired_publication import evidence

    binding = read(root / "binding.json")
    pair, _ = assignments()
    if (binding["physical_score_sha256"] != authorized(physical) or binding["order"] != list(ORDER)
            or binding["request"]["archive"] != pair["archive"] or binding["request"]["region_file"] != pair["region"]):
        raise ValueError("Public pair differs from its frozen assignment")
    old = read(checked(HERE / "measurements/north-combined.json", REFERENCE_SHA))["cases"]
    original = read(checked(ORIGINAL / "joint-research-receipt.json", ORIGINAL_SHA))
    refs = read(checked(HERE.parent / "regional-release/scoring-key.json", TRUTH_SHA))["answers"]
    truth, = {tuple(v["truth"]) for v in refs.values() if v["recording"] == NORTH}
    settings = dict(counts=old["containing"]["counts"], grid_points=137, regional_pin=TRACK_SCORES_SHA)
    before, left, control = read_run(root, "12ms", binding, truth, **settings)
    after, right, trial = read_run(root, "8ms", binding, truth, **settings)
    verified = evidence(ORIGINAL, original["receipt"], 0, read_only=True)
    if (before["decision"] != "complete" or before["native_sha256"] != old["containing"]["native_sha256"]
            or before["terminal_sha256"] != old["containing"]["terminal_sha256"]
            or before["publication"]["images"] != old["containing"]["images"]
            or before["scientific_digests"] != verified["scientific_digests"]
            or control["selected_rows"] != original["selected_rows"]):
        raise ValueError("Fresh North 12 ms science differs from the original publication")
    stock = old["stock"]
    stock["errors_km"] = {a: stock["score"]["arms"][a]["error_km"] for a in ARMS}
    stock["arms"] = {a: {k: stock["score"]["arms"][a][k] for k in ("latlon", "rf_rms_hz")} for a in ARMS}
    position = quality(after["errors_km"], {"12ms": before["errors_km"], "v3": stock["errors_km"]},
                       complete=after["decision"] == "complete")
    return dict(case="north-containing", survey=truth, survey_sha256=TRUTH_SHA, original_pair_sha256=REFERENCE_SHA,
                binding=binding, runs={"12ms": before, "8ms": after, "v3": stock}, position=position,
                **comparison(left, right, control, trial))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    launch = sub.add_parser("run")
    for name in ("root", "physical", "short", "eight", "geographic", "regional"):
        launch.add_argument(name, type=Path)
    verify = sub.add_parser("score")
    for name in ("root", "physical", "output"):
        verify.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    if args.pop("action") == "run":
        run(**args)
    else:
        write(args.pop("output"), score(**args))
