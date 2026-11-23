"""Run or score the regional likelihood option through the ordinary saved publication."""

import argparse
import gzip
import json
from pathlib import Path

from aperture_trial import read, write
from cold_track_row_transfer import GEOGRAPHIC, SMALL, small_inputs
from dense_geographic_trial import host
from full_short_run import TRACK_SCORES_SHA
from full_short_south import invoke

HERE = Path(__file__).resolve().parent
CONTROL = Path("/var/tmp/leo-cold-track-transfer.vheDHqDH")


def replay(case, library, root):
    host()
    (recording, archive, region, packet, pin, _), _ = small_inputs("south-far" if case == "south-near" else case)
    if case == "south-near":
        from full_short_graph_transfer import SOUTH
        from full_short_south import FAR, checked

        control = checked(FAR, "5181abf1c8a36d45dfe140e8851f0a423b69ec69b8ca231a3f87bcc9fdcecca9")
        region = SOUTH / "near-offer.json"
        if read(region) != control["results"]["south-mirror-outside"]["offer"]:
            raise ValueError("The near-omission offer changed")
    flags = ["--recording", recording, "--archive", archive["root"], "--region", region,
             "--saved", packet, "--saved-digest", pin, "--output", root / case, "--track-graph", "installed",
             "--geographic-library", GEOGRAPHIC, "--regional-track-library", library,
             "--reuse-grid-phase-states", "--reuse-cold-track-rows"]
    write(root / f"process-{case}.json", invoke(flags))


def score(root):
    from grid_phase_entry_score import check
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    archived = json.loads(gzip.decompress((HERE / "measurements/cold-track-row-transfer.json.gz").read_bytes()))
    rows = {}
    for case in SMALL:
        directory = root / case
        trial = read(directory / "joint-research-receipt.json")
        recipe = read(directory / "full-short-recipe.json")
        count = trial["solve"]["geographic_projector"]
        proof, = trial["early_regional"]
        result = proof["result"]
        identifier = trial["receipt"]["run_id"]
        terminal = read(directory / "fast-scan-automatic-work" / identifier / "terminal.json")
        if (recipe["regional_track_sha256"] != TRACK_SCORES_SHA or count["track_score_native"] != result["probes_evaluated"]
                or count["track_score_fallbacks"] or trial["receipt"]["terminal_sha256"] != canonical_digest(terminal)):
            raise ValueError("Unbound publication or regional score")
        if case == "physical":
            parity = check(directory, CONTROL / case)
        else:
            control = archived[case]["documents"]["joint-research-receipt.json"]
            expected = control["early_regional"][0]["result"]
            from dense_geographic_trial import difference
            matched = difference(result, expected) <= 1e-10
            parity = dict(proof=matched, terminal=terminal["decision"] == "withheld",
                          reason=terminal["reason"] == "both_receivers_support_far_exterior",
                          packet=trial["saved_digest"] == control["saved_digest"],
                          run=identifier == control["receipt"]["run_id"],
                          no_owners=not trial["selected_rows"], no_fit=trial.get("route_details") is None,
                          no_figures=not FastStandardAnalysisStore(directory).detail(identifier)["artifacts"])
            if not all(parity.values()):
                raise ValueError(f"Southern terminal changed: {parity}")
        rows[case] = dict(parity=parity, proof=result, projection=count, packet=trial["saved_digest"],
                          terminal_sha256=trial["receipt"]["terminal_sha256"], solve_cpu_s=trial["solve"]["cpu_s"],
                          publication_cpu_s=trial["publication_cpu_s"], process=read(root / f"process-{case}.json"))
    return rows


def score_near(root):
    from aperture_score import distance_km, references
    from full_short_south import FAR, checked
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from mixture_score import section
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km

    control = checked(FAR, "5181abf1c8a36d45dfe140e8851f0a423b69ec69b8ca231a3f87bcc9fdcecca9")["results"]["south-mirror-outside"]
    earlier = checked(HERE / "measurements/full-short-south.json",
                      "607b25b2352393103db2f05d5fe8f36ae2a7dafbc04b1328d7db792516cfd356")["cases"]["near"]
    directory = root / "south-near"
    run = read(directory / "joint-research-receipt.json")
    receipt = run["receipt"]
    terminal = read(directory / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json")
    proof, = run["early_regional"]
    counts = run["solve"]["geographic_projector"]
    recipe = read(directory / "full-short-recipe.json")
    figures = json.loads(json.dumps(artifacts(directory, receipt)))
    if (receipt["region"] != control["offer"] or terminal["region"] != control["offer"]
            or terminal["native_sha256"] != run["saved_digest"] or run["saved_digest"] != earlier["native_pin"]
            or receipt["terminal_sha256"] != canonical_digest(terminal) or figures != run["evidence"]
            or recipe["regional_track_sha256"] != TRACK_SCORES_SHA or recipe["graph"] != "installed"
            or counts["track_score_fallbacks"] or counts["track_score_native"] != proof["result"]["probes_evaluated"]):
        raise ValueError("Near-omission publication differs from the original packet, offer or implementation")
    truth = references()["south-containing"]
    clearance = face_clearance_km(receipt["region"], truth)
    if abs(clearance - control["truth_clearance_km"]) > 1e-9:
        raise ValueError("Scoring location changed")
    inside = read(HERE / "measurements/full-short-graph-transfer.json")["south-inside"]
    if inside["terminal"]["native_sha256"] != run["saved_digest"]:
        raise ValueError("Containing comparison requires identical waveforms and receiver")
    changes = {}
    for arm, estimate in terminal["arms"].items():
        previous = inside["terminal"]["arms"][arm]["latlon"]
        current = estimate.get("latlon")
        changes[arm] = dict(inside_estimated_clearance_km=face_clearance_km(inside["receipt"]["region"], previous),
                            outside_estimated_clearance_km=face_clearance_km(receipt["region"], current) if current else None,
                            estimate_displacement_m=1000 * distance_km(previous, current) if current else None)
    return dict(decision=receipt["decision"], status=terminal["decision"], clearance_km=clearance,
                native_pin=run["saved_digest"], terminal_sha256=receipt["terminal_sha256"],
                original_v3=control, quadratic=earlier["score"], candidate=section(terminal["arms"], truth, control["arms"]),
                owners={k: len(v) for k, v in run["selected_rows"].items()}, figure_digests=figures,
                grid_points=run["solve"].get("grid_points"), proof=proof["result"], counts=counts, face_shift=changes,
                process=read(root / "process-south-near.json"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=(*SMALL, "south-near", "score", "score-near"))
    parser.add_argument("root", type=Path)
    parser.add_argument("file", type=Path, help="Shared library for replay or fresh JSON output for scoring")
    args = parser.parse_args()
    if args.case in ("score", "score-near"):
        write(args.file, (score if args.case == "score" else score_near)(args.root))
    else:
        replay(args.case, args.file, args.root)
