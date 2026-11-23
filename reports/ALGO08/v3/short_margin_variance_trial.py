"""Run and score the two saved short-margin likelihood pairs."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

from short_margin_variance import Trial, variance_factors


HERE = Path(__file__).resolve().parent
MODES = ("unit", "weighted")
CASES = ("physical", "north")
GEOGRAPHIC = Path("/var/tmp/leo-dense-short-pins.0zaX7eSH/geographic.so")
NORTH_TRACKS = Path("/var/tmp/leo-regional-track.O238AD0C/scores.so")


def worker(case, mode, output):
    from aperture_trial import configuration, write

    runtime = configuration()
    from discovery_margin_trial import packet_pin, verified_input
    from full_short_run import RECIPE_SHA, geographic_projection
    from tools.pipeline_eval.variants.track_preparation import fingerprint
    import joint_publication

    binding, packet, native = verified_input(case, "12ms")
    offer = binding["request"]
    factors, census = variance_factors(native)
    trial = Trial(factors, weighted=mode == "weighted")
    graph = []

    def observe(prepared):
        graph.append(fingerprint(prepared["tracks"]))
        return dict(graph_sha256=graph[-1])

    args = SimpleNamespace(recording=Path(offer["recording"]), archive=Path(offer["archive"]["root"]),
                           region=Path(offer["region_file"]), saved=packet, saved_digest=packet_pin(case, "12ms"),
                           output=output, optimized_full_catalogue=True, verify_images=True, observe_prepared=observe)

    def projection():
        return geographic_projection(GEOGRAPHIC, NORTH_TRACKS if case == "north" else None)

    with (patch.object(joint_publication, "configuration", return_value=runtime), trial.install()):
        result = joint_publication.run(args, early_regional=True, keep_selected_rows=True, saved_receiver=RECIPE_SHA,
                                       geographic_projector=projection, reuse_cold_rows=True, reuse_grid_phase_states=True)
    if len(graph) != 1:
        raise ValueError("Expected the original single complete graph")
    write(output / "short-margin-variance.json", dict(mode=mode, case=case, offered_region=offer["offered_region"],
          saved=args.saved_digest, graph_sha256=graph[0], census=census, authority=offer["raw_authority"],
          terminal=result["receipt"]["terminal_sha256"], **trial.summary()))


def score(root):
    from aperture_trial import ARMS, read
    from dense_full_short_raw import checked
    from discovery_margin_score import geography
    from discovery_margin_trial import packet_pin
    from eight_ms_crossover import CASE_ROOTS, RAW_REPORT_PINS
    from eight_ms_physical_score import quality
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.presentation.localization_v3 import owner_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_cli_trial import native_packet
    from mixture_score import section
    from signed_0374_transfer import owner_changes
    from tools.pipeline_eval.qualification.paired_publication import evidence

    cases = {}
    for case in CASES:
        folder = root / case
        archived = read(checked(HERE / "measurements" / f"eight-ms-{case}.json", RAW_REPORT_PINS[case]))
        known = archived["runs"]
        stock = known["12ms"]
        original = read(CASE_ROOTS[case] / "12ms/joint-research-receipt.json")
        results, proofs = {}, {}
        for mode in MODES:
            output = folder / mode
            proof = read(output / "joint-research-receipt.json")
            trial = read(output / "short-margin-variance.json")
            clock = read(folder / f"{mode}-clock.json")
            receipt = proof["receipt"]
            scientific = evidence(output, receipt, 0, read_only=True)
            publication = json.loads(json.dumps(artifacts(output, receipt)))
            if (clock["status"] or trial["saved"] != packet_pin(case, "12ms")
                    or scientific["raw_authority"] != trial["authority"] or receipt["region"] != trial["offered_region"]
                    or receipt["terminal_sha256"] != trial["terminal"] or proof["evidence"] != publication
                    or canonical_digest(read(native_packet(output))) != trial["saved"]
                    or receipt["counts"] != stock["counts"]):
                raise ValueError(f"{case} {mode} does not bind the original saved acquisition")
            if receipt["decision"] == "complete":
                store = FastStandardAnalysisStore(output)
                grid = store.position_grid(receipt["run_id"])
                if (not grid["complete"] or grid["evaluated_points"] != grid["planned_points"]
                        or mode == "unit" and grid["evaluated_points"] != stock["grid_points"]
                        or len(publication["images"]) != 8):
                    raise ValueError(f"{case} {mode} omitted original grid coverage or a figure")
                for arm, rows in proof["selected_rows"].items():
                    ids = {oid: value for oid, value, _ in rows}
                    if len(ids) != len(rows) or owner_digest(ids) != scientific["owners"][arm]:
                        raise ValueError("Published owner rows did not bind the official owner map")
                for name in ("path", "grid"):
                    if getattr(store, "position_" + name)(receipt["run_id"])["binding"]["position_png_sha256"] != publication["images"]["position"]["sha256"]:
                        raise ValueError("Position sidecar did not verify its official image")
            position = section(scientific["arms"], archived["survey"], known["v3"]["arms"])
            gate = quality({arm: position["arms"][arm]["error_km"] for arm in ARMS},
                           {"v3": known["v3"]["errors_km"]}, complete=receipt["decision"] == "complete")
            results[mode] = dict(trial=trial, science=scientific, figures=publication, terminal=receipt["terminal_sha256"],
                                 solve=proof["solve"], process=clock, phase=proof["route_details"].get("signed"),
                                 geography=geography(proof), position=position, gate=gate,
                                 receipt_sha256=sha256((output / "joint-research-receipt.json").read_bytes()).hexdigest())
            proofs[mode] = proof

        unit, weighted = (results[mode] for mode in MODES)
        if (unit["terminal"] != stock["terminal_sha256"] or unit["science"]["arms"] != stock["arms"]
                or unit["science"]["owners"] != stock["owner_sha256"]
                or unit["science"]["scientific_digests"] != stock["scientific_digests"]
                or any(unit["figures"][key] != stock["publication"][key] for key in ("images", "path"))
                or unit["geography"] != geography(original)
                or proofs["unit"]["selected_rows"] != original["selected_rows"] or not unit["trial"]["accepted"]):
            raise ValueError("The unit likelihood did not reproduce the original publication")
        if (unit["trial"]["graph_sha256"] != weighted["trial"]["graph_sha256"]
                or unit["trial"]["selected_support"] != weighted["trial"]["selected_support"]
                or unit["trial"]["selected_support"]["ordinary"] != unit["trial"]["selected_support"]["after_signed"]):
            raise ValueError("The measurement trial altered the original Graph or its curved and predictive support")
        weighted["vs_unit"] = section(weighted["science"]["arms"], archived["survey"], unit["science"]["arms"])
        replay = weighted["solve"].get("objective_replay", {})
        checks = dict(signed=weighted["trial"]["accepted"],
                      applied=all(weighted["trial"]["scopes"].get(stage, {}).get(arm, {}).get(role, {}).get("changed", 0) > 0
                                  for stage in ("signed", "evidence") for arm in ARMS for role in ("curved", "predictive")),
                      replay=set(replay) == set(ARMS) and all(abs(x) <= 1e-5 for x in replay.values()))
        cases[case] = dict(runs=results, checks=checks, owner_changes=owner_changes(proofs["unit"], proofs["weighted"]),
                           prior_sha256=RAW_REPORT_PINS[case], reference_errors_km=known["v3"]["errors_km"])
    return dict(cases=cases, passed=all(all(data["checks"].values()) and data["runs"]["weighted"]["gate"]["passes"]
                                      for data in cases.values()))


def run(root):
    from aperture_trial import RELEASE, write
    from dense_full_short_raw import checked
    from dense_geographic_trial import host
    from full_short_physical import environment
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA
    from weak_combined_raw import measure

    machine = host()
    checked(GEOGRAPHIC, GEOGRAPHIC_SHA)
    checked(NORTH_TRACKS, TRACK_SCORES_SHA)
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use fresh local tmpfs for the saved pair")
    root.mkdir()
    (root / "tmp").mkdir()
    env = environment(root)
    env["TMPDIR"] = str(root / "tmp")
    python = str(RELEASE / "venv/bin/python")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    for case in CASES:
        folder = root / case
        folder.mkdir()
        for mode in MODES:
            command = [python, "-BPs", str(Path(__file__).resolve()), "worker", case, mode, str(folder / mode)]
            measure(command, env, folder, mode)
    # Open position references only after every scientific route and figure is sealed.
    write(root / "result.json", dict(machine=machine, order=MODES, **score(root),
          source_sha256={name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
              "short_margin_variance.py", "short_margin_variance_trial.py", "short-margin-variance-protocol.md",
          )}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="action", required=True)
    child = modes.add_parser("worker")
    child.add_argument("case", choices=CASES)
    child.add_argument("mode", choices=MODES)
    child.add_argument("output", type=Path)
    modes.add_parser("run").add_argument("root", type=Path)
    values = vars(parser.parse_args())
    {"run": run, "worker": worker}[values.pop("action")](**values)
