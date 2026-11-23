"""Run and score the original and native regional-track options on one dense saved packet."""

import argparse
import json
import os
from pathlib import Path
import subprocess

from aperture_trial import ARMS, RELEASE, archive_identity, read, write
from cold_track_row_transfer import DENSE, GEOGRAPHIC, RAW, numeric_grid, same_route
from cold_track_row_trial import REPLAY_PIN
from dense_full_short_crossover import file_sha
from dense_geographic_trial import difference, host
from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA
from full_short_south import invoke

ORDER = ("native", "original")


def reference():
    if file_sha(DENSE) != REPLAY_PIN:
        raise ValueError("Archived numerical reference changed")
    return read(DENSE)


def run(root, library):
    system = host()
    raw = reference()["raw"]
    identity = raw["holder"]
    binding = raw["binding"]
    packet, = (RAW / "publication/fast-scan-automatic-work").glob("*/detections.json")
    pin = raw["raw_native_sha256"]
    region = Path(binding["region"])
    archive = Path(identity["archive"]["root"])
    if (archive_identity(archive) != identity["archive"] or read(region) != identity["offer"]
            or file_sha(region) != identity["offer_source_sha256"] or file_sha(packet) != pin.removeprefix("sha256:")
            or file_sha(library) != TRACK_SCORES_SHA or file_sha(GEOGRAPHIC) != GEOGRAPHIC_SHA):
        raise ValueError("Changed input, region, archive, or native library")
    recording = binding["command"][binding["command"].index("--recording") + 1]
    root.mkdir()
    os.environ["MPLCONFIGDIR"] = str(root / "fonts")
    subprocess.run([RELEASE / "venv/bin/python", "-Bc",
                    "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"], check=True)
    flags = ["--recording", recording, "--region", region, "--archive", archive, "--saved", packet, "--saved-digest", pin,
             "--track-graph", "installed", "--geographic-library", GEOGRAPHIC, "--reuse-cold-track-rows", "--reuse-grid-phase-states"]
    write(root / "binding.json", dict(order=ORDER, host=system, archive=identity["archive"], offer=identity["offer"],
                                      packet_sha256=pin, geographic_sha256=GEOGRAPHIC_SHA, regional_sha256=TRACK_SCORES_SHA))
    for arm in ORDER:
        options = ["--regional-track-library", library] if arm == "native" else []
        write(root / f"{arm}-process.json", invoke([*flags, "--output", root / arm, *options]))


def score(root):
    from aperture_score import distance_km, references
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.contracts.fast_standard_analysis import PLOTS
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    ref = reference()
    bind = read(root / "binding.json")
    truth = references()["DS30-0008"]
    rows, products = {}, {}
    for arm in ORDER:
        directory = root / arm
        report = read(directory / "joint-research-receipt.json")
        recipe = read(directory / "full-short-recipe.json")
        receipt = report["receipt"]
        identifier = receipt["run_id"]
        store = FastStandardAnalysisStore(directory)
        grid, path = store.position_grid(identifier), store.position_path(identifier)
        science = {k: canonical_digest({key: value for key, value in data.items() if key not in ("binding", "elapsed_seconds")})
                   for k, data in (("grid", grid), ("path", path))}
        terminal = read(directory / "fast-scan-automatic-work" / identifier / "terminal.json")
        actual = json.loads(json.dumps(artifacts(directory, receipt)))
        proof, = report["early_regional"]
        solve = report["solve"]
        checks = dict(
            input=report["saved_digest"] == terminal["native_sha256"] == bind["packet_sha256"] == ref["raw"]["raw_native_sha256"],
            region=receipt["region"] == terminal["region"] == bind["offer"] == ref["raw"]["holder"]["offer"],
            receipt=canonical_digest(terminal) == receipt["terminal_sha256"] == store.detail(identifier)["terminal_sha256"],
            terminal=receipt["decision"] == "complete" and terminal["arms"] == ref["arms"] and terminal["reason"] == ref["reason"],
            owners=report["selected_rows"] == ref["selected_rows"],
            grid=grid["complete"] and grid["evaluated_points"] == ref["grid_points"] == 179 and science == ref["science"],
            route=same_route(report["route_details"], ref["attempts"][0]) and terminal["orbit_policy"] == ref["orbit_policy"],
            proof=difference(proof["result"], ref["regional"][0]["result"]) <= 1e-10,
            figures=actual == report["evidence"] and set(actual["images"]) == set(PLOTS),
            options=(recipe["graph"] == "installed" and recipe["reuse_grid_phase_states"] and recipe["reuse_cold_track_rows"]
                     and recipe.get("regional_track_sha256") == (TRACK_SCORES_SHA if arm == "native" else None)
                     and solve["cold_track_rows"]["reused_requests"] > 0 and solve["predictive_phase_states"]["prepared_calls"] == 356),
            scorer=solve["geographic_projector"].get("track_score_native", 0) == (25 if arm == "native" else 0)
                   and not solve["geographic_projector"].get("track_score_fallbacks", 0),
        )
        if not all(checks.values()):
            raise ValueError(f"{arm} scientific verification failed: {checks}")
        products[arm] = dict(terminal=terminal, grid=numeric_grid(grid), path=path, images=actual["images"])
        rows[arm] = dict(checks=checks, process=read(root / f"{arm}-process.json"), terminal_sha256=receipt["terminal_sha256"],
            publication_cpu_s=report["publication_cpu_s"], publication_elapsed_s=report["publication_elapsed_s"],
            solve_cpu_s=solve["cpu_s"], solve_elapsed_s=solve["elapsed_s"], proof_cpu_s=proof["cpu_s"],
            cold_cpu_s=report["route_details"]["cold_clocks"]["cpu_s"],
            grid_cpu_s=report["route_details"]["standard_evidence_clocks"]["cpu_s"],
            signed_cpu_s=report["route_details"]["signed_total_clocks"]["cpu_s"],
            images=actual["images"], proof=proof["result"], projection=solve["geographic_projector"],
            arms=terminal["arms"], owners=ref["associated"], science=science,
            horizontal_error_km={a: distance_km(terminal["arms"][a]["latlon"], truth) for a in ARMS})
    if products["original"] != products["native"]:
        raise ValueError("The two complete numerical and PNG publications differ")
    return dict(binding=bind, same_complete_science=True, runs=rows)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("run", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("file", type=Path)
    args = cli.parse_args()
    if args.mode == "run":
        run(args.root, args.file)
    else:
        write(args.file, score(args.root))
