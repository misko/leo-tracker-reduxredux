"""Replay the archived adaptive publication with a single signed-first attempt."""

import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from signed_first_finish import binding


PINS = dict(blind_joint_finish="7d8d5a65ceb0e11150e28d0dbbddeabb7741ef1408ded6272500e4f0e012c708",
            blind_joint_route="f7a66aea7ed875f5de067a0125948cd51c91e329ac0ea4b4ab1b4da6db5d1ca6",
            blind_joint_signed="3ec955b211a1c4b48fe18c66d9374a78fd393d3b068ffed1c7a9fe42d035629b",
            isolated_salvage="868bc79aa30e4548bd7979a79e458117583f4941cc374a8343568dc0a767d771",
            named_survivor_fit="32b4f05449f6e4e0316d66b214a0564dfe4c14acfa413664e89333f40d8c1c2e")
CASES = {
    "DS30-0316": (Path("/dev/shm/leo-v3-live-adaptive-grid-medium01"), "portable", "portable.clock.json",
                  "saved-0316-worker.json", "7cf9d373642a4cbd60b999f0638a230d02c2fb0894f80e677dbacaef34f31b66",
                  "18d1c02428d9cc068a2b3b454f4018f3a0e26737473f2f7b9afa5dd59ab967b3"),
    "DS30-0008": (Path("/dev/shm/leo-v3-live-adaptive-grid-result01"), "candidate", "clock.json",
                  "dense-hybrid-combined-worker.json", "4980d2c33a8809b6c7653e83251358c68f653befd646c0ec6367c51c8fe1a482",
                  "a0205c691d44f885a7d2ca02e2e9602ec6acd978b609ae0379926243fbaf7fd4"),
}


def enroll(case):
    import live_adaptive_grid_trial as adaptive

    root, leaf, clock, _worker, result_pin, trace_pin = CASES[case]
    if (adaptive.pin(root/"result.json") != result_pin
            or adaptive.pin(root/leaf/"joint-research-receipt.json") != trace_pin):
        raise ValueError("Original adaptive science or branch receipt changed")
    result = adaptive.read(root/"result.json")
    if (not result["match"] or not result["layout"]["audit"]["passed"]
            or result["clocks"]["adaptive"] != adaptive.read(root/clock)):
        raise ValueError("Require the original successful and scored adaptive publication")
    return adaptive, root


def launch(case, fresh, screen=None):
    adaptive, root = enroll(case)
    from aperture_trial import RELEASE
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    medium = case == "DS30-0316"
    if not medium:
        result = adaptive.read(screen/"comparison.json")
        if result["case"] != "DS30-0316" or not result["eligible_transfer"]:
            raise ValueError("Dense transfer requires the frozen medium speed and science gate")
    if fresh.parent.resolve(strict=True) != Path("/dev/shm") or fresh.exists():
        raise ValueError("Use a new private tmpfs result")
    if medium:
        sys.path.insert(0, str(adaptive.MEDIUM_SOURCE))
        from portable_orbit_0316_repair import admitted
        admitted()
        expected_sources = adaptive.medium_pins()
    else:
        expected_sources = adaptive.source_pins(adaptive.read(root/"binding.json"))
    original = adaptive.read(root/"research-binding.json")
    if expected_sources != original["experiment"]:
        raise ValueError("Require the identical archived adaptive source and configuration")
    fresh.mkdir(mode=0o700)
    for name in ("tmp", "fonts"):
        (fresh/name).mkdir()
    for path in (root/"fonts").glob("fontlist-*.json"):
        (fresh/"fonts"/path.name).write_bytes(path.read_bytes())
    if not medium:
        (fresh/"binding.json").write_bytes((root/"binding.json").read_bytes())
    (fresh/"research-binding.json").write_bytes((root/"research-binding.json").read_bytes())
    command = ["/usr/bin/timeout", "--kill-after=2s", "60s", RELEASE/"venv/bin/python", "-IB",
               Path(__file__).resolve(), "worker", case, fresh]
    file_pins = {name: adaptive.pin(HERE/name) for name in (
        "signed_first_trial.py", "signed_first_finish.py", "signed-first-finish-protocol.md")}
    adaptive.write(fresh/"schedule-binding.json", dict(case=case, source=file_pins, runtime_pins=PINS, machine=host(),
                  archived_control_pins=dict(result=CASES[case][4], trace=CASES[case][5]), command=list(map(str, command))))
    env = environment(fresh) | {"TMPDIR": str(fresh/"tmp"), "XDG_CACHE_HOME": str(fresh/"tmp")}
    adaptive.write(fresh/"clock.json", measure(command, env, fresh/CASES[case][1]))


def worker(case, fresh):
    adaptive, _control = enroll(case)
    medium = case == "DS30-0316"
    if medium:
        sys.path.insert(0, str(adaptive.MEDIUM_SOURCE))
    import unified_short_bootstrap as bootstrap

    enrolled = adaptive.read(fresh/"schedule-binding.json")
    if (enrolled["case"] != case or enrolled["runtime_pins"] != PINS
            or any(adaptive.pin(HERE/name) != pin for name, pin in enrolled["source"].items())):
        raise ValueError("The research mechanism changed after enrollment")
    original = bootstrap.publish_active

    def publication(opts, *args, **kwargs):
        import importlib

        if opts.output != fresh/CASES[case][1] or not opts.named_survivor_finish:
            raise ValueError("Only the enrolled named-finish saved publication may call the schedule")
        for name, pin in PINS.items():
            if adaptive.pin(Path(importlib.import_module(name).__file__)) != pin:
                raise ValueError(f"The archived dependency {name} changed")
        import named_survivor_fit as named

        with patch.object(named, "binding", lambda witness: binding(witness, fallback_binding=ordinary)):
            return original(opts, *args, **kwargs)

    import named_survivor_fit as named_module
    ordinary = named_module.binding
    with patch.object(bootstrap, "publish_active", publication):
        (adaptive.medium_worker if medium else adaptive.worker)(fresh)


def product(root, run):
    from joint_publication import figure_evidence
    from leo.contracts.digests import sha256_digest
    from reports.ALGO08.v3.live_adaptive_grid_entry import read_manifest, read_sidecar, research_folder

    manifest = read_manifest(root, run)
    sample, path = (read_sidecar(root, run, name) for name in ("sample", "path"))
    figure_folder = research_folder(root, run)
    figures = {}
    for entry in manifest["publication"]["artifacts"]:
        intended = entry["sha256"]
        data = (figure_folder/(intended[7:]+".png")).read_bytes()
        if sha256_digest(data) != intended or len(data) != entry["byte_count"]:
            raise ValueError("Published PNG differs from the manifest")
        figures[entry["name"]] = figure_evidence(data, intended)
    if len(figures) != 8 or sample["binding"]["terminal_sha256"] != manifest["publication"]["terminal_sha256"]:
        raise ValueError("Missing figure or mismatched adaptive terminal")
    return manifest, sample, path, figures


def compare(case, fresh):
    adaptive, control = enroll(case)
    from leo.contracts.digests import canonical_digest
    from portable_orbit_0316_repair import without_timers
    from prospective_0316_solver import owner_delta
    from triage_bounds import calibration_comparison

    leaf, clock_file, worker_file, *_ = CASES[case][1:]
    before, after = adaptive.read(control/clock_file), adaptive.read(fresh/"clock.json")
    result = dict(case=case, archived_paid_control=before, signed_first_child=after,
                  eligible_transfer=False, original_waveform_reads=0)
    if after["exit_code"]:
        return result
    old_root, new_root = control/leaf, fresh/leaf
    baseline, candidate = [adaptive.read(root/"joint-research-receipt.json") for root in (old_root, new_root)]
    old, new = [adaptive.read(root/worker_file) for root in (old_root, new_root)]
    if (old["native_sha256"] != new["native_sha256"] or not all(row["handoffs"] == 1 for row in (old, new))
            or new.get("waveform_calls", 0) or not new.get("no_waveform", True)):
        raise ValueError("Comparison changed signed measurements or opened acquisition")
    same = dict(region=old["receipt"]["region"] == new["receipt"]["region"],
                proofs=without_timers(baseline["early_regional"]) == without_timers(candidate["early_regional"]),
                terminal=old["receipt"]["terminal_sha256"] == new["receipt"]["terminal_sha256"],
                decision=old["receipt"]["decision"] == new["receipt"]["decision"],
                owners=baseline["selected_rows"] == candidate["selected_rows"])
    details = candidate["route_details"]
    result.update(same=same, old_route=ordinary_costs(baseline["route_details"]), new_route=ordinary_costs(details),
                  attempt=details.get("signed_first"), exterior=details.get("exterior"),
                  decisions=[row["receipt"]["decision"] for row in (old, new)], detector=new["native_sha256"],
                  cpu_s_saved=before["cpu_s"]-after["cpu_s"], wall_s_saved=before["elapsed_s"]-after["elapsed_s"])
    if new["receipt"]["decision"] != "complete":
        return result
    (base, grid, path, images), (test, new_grid, new_path, new_images) = [
        product(root, row["receipt"]["run_id"]) for root, row in ((old_root, old), (new_root, new))]
    a, b = base["publication"], test["publication"]
    if canonical_digest(a) != base["publication_sha256"] or canonical_digest(b) != test["publication_sha256"]:
        raise ValueError("Invalid science manifest")
    def grid_science(value):
        return without_timers({key: row for key, row in value.items() if key not in {"sample_cpu_s", "refinement_cpu_s"}})

    same.update(arms=a["arms"] == b["arms"], grid=grid_science(grid) == grid_science(new_grid),
                path=without_timers(path) == without_timers(new_path), phase=base["phase_state_sha256"] == test["phase_state_sha256"],
                exact_pngs=images == new_images, geographic_decision=without_timers(baseline["route_details"]["exterior"]) ==
                    without_timers(details["exterior"]))

    controls = {}
    for mode, root, receipt in (("control", old_root, old["receipt"]), ("signed_first", new_root, new["receipt"])):
        controls[mode] = adaptive.read(root/"fast-scan-automatic-work"/receipt["run_id"]/"terminal.json")
        if canonical_digest(controls[mode]) != receipt["terminal_sha256"] or controls[mode]["native_sha256"] != (
                "sha256:" + new["native_sha256"].removeprefix("sha256:")):
            raise ValueError("The genuine terminal changed or points to another signed input")

    medium = case == "DS30-0316"
    if medium:
        sys.path.insert(0, str(adaptive.MEDIUM_SOURCE))
        finishes = adaptive.medium_checks(control, fresh, baseline, candidate)
        png = adaptive.read(new_root/"final-fit-options.json")["png_readback"]
    else:
        finishes = adaptive.dense_checks(control, fresh, (old, new))
        png = new["png"]
    same.update(named_activation=finishes[0] == finishes[1] and finishes[1]["paid_final_fit"],
                verified_reads=png["verified"] == png["reused"] == 8 and not png["fallbacks"])
    result.update(geography=calibration_comparison(controls, case), terminal_arms={mode: row["arms"] for mode, row in controls.items()},
                  figure_residual_rms_hz={mode: {arm: row["residual_rms_hz"] for arm, row in document["arms"].items()}
                                         for mode, document in (("control", a), ("signed_first", b))},
                  original_grid_points=grid["evaluated_points"], candidate_grid_points=new_grid["evaluated_points"], figures=new_images,
                  owner_counts={arm: len(rows) for arm, rows in candidate["selected_rows"].items()},
                  owner_changes={arm: owner_delta(baseline["selected_rows"][arm], rows)
                                 for arm, rows in candidate["selected_rows"].items()})
    result["eligible_transfer"] = bool(medium and all(same.values()) and details.get("signed_first", {}).get("status") == "accepted"
                                       and details["signed_first"]["pair_calls"] == 1 and "finish_clocks" not in details
                                       and min(result["cpu_s_saved"], result["wall_s_saved"]) >= .050)
    return result


def ordinary_costs(route):
    trial = route.get("provisional_salvage", {})
    signed = route.get("named_survivor_fit", {})
    return dict(ordinary=route.get("finish_clocks"), ordinary_passed=route.get("pair_passes"),
                repair_preparation=route.get("repair_prepare_clocks"), repair_pair=route.get("repair_fit_clocks"),
                endpoint=trial.get("endpoint_trim", route.get("endpoint_trim")),
                provisional_status=trial.get("status"), repair_status=route.get("repair", {}).get("status"),
                late_signed=route.get("signed_total_clocks"), named_arms=signed.get("named_arm_clocks"),
                standard_evidence=route.get("standard_evidence_clocks"), inference_fallback=route.get("fallback_clocks"),
                cold=route.get("cold_clocks"), initial_gate=route.get("initial_gate_clocks"), salvage=route.get("salvage_clocks"),
                predictive=route.get("predictive_clocks"), through_inference_proposal=route.get("candidate_pre_evidence_clocks"))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "worker", "compare"))
    cli.add_argument("case", choices=CASES)
    cli.add_argument("root", type=Path)
    cli.add_argument("--medium-screen", type=Path)
    args = cli.parse_args()
    if args.action == "compare":
        import live_adaptive_grid_trial as adaptive
        adaptive.write(args.root/"comparison.json", compare(args.case, args.root))
    elif args.action == "launch":
        launch(args.case, args.root, args.medium_screen)
    else:
        worker(args.case, args.root)
