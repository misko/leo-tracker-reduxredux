"""Replay the paired live dense worker with a separate adaptive research sink."""

import argparse
from hashlib import file_digest, sha256
import json
from pathlib import Path
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SOURCE = Path("/dev/shm/leo-v3-dense-hybrid-combined/reports/ALGO08/v3")
CONTROL = Path("/dev/shm/leo-v3-dense-hybrid-combined-result01")
NATIVE = "sha256:161d3ff4a85777f81217a929fdf0c999eb09f48575322ab46dcdcd773a95e23a"
MEDIUM_SOURCE = Path("/dev/shm/leo-v3-block-portable-0316/reports/ALGO08/v3")
MEDIUM_CONTROL = Path("/dev/shm/leo-v3-block-portable-0316-result01")
MEDIUM_NATIVE = "6bbbb2575df6a203dd0d183a3ad8390110fbac778504803e275b7493b8422bed"
MEDIUM_PINS = {"combined-verified.json": "e8a4fad9eea4ee7381d4717f1f3c52423a9b643d0225207cf374b5f461a78196",
               "portable.clock.json": "d06b23219869735b2e848ab999f6239bf8491f776377c2fe01fa45402f5965f1",
               "portable/saved-0316-worker.json": "0eec5317dafa4f4fa928b6e70a57826acc8f0a415688df5186dddbc4aea04e8b"}
MEDIUM_PROTOCOL = HERE/"live-adaptive-grid-medium-protocol.md"
EXPERIMENT = (Path(__file__), HERE/"live_adaptive_grid.py", HERE/"live_adaptive_grid_entry.py", HERE/"live-adaptive-grid-protocol.md")
RECEIPT_SCIENCE = ("run_id", "session_id", "window_count", "counts", "region", "decision", "terminal_sha256")
sys.path[:0] = [str(SOURCE), str(HERE.parents[2])]


def pin(path):
    with path.open("rb") as handle:
        return file_digest(handle, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, data):
    with path.open("x") as stream:
        json.dump(data, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def source_pins(job):
    if (job["request"]["native"] != NATIVE or any(pin(SOURCE/k) != v for k, v in job["source_sha256"].items())):
        raise ValueError("The enrolled source or complete hybrid native packet changed")
    return {p.name: pin(p) for p in EXPERIMENT}


def worker(root):
    import dense_hybrid_combined
    import raw_cfo_north_trial
    from reports.ALGO08.v3.live_adaptive_grid_entry import research_layout

    job = root/"binding.json"
    identity = read(root/"research-binding.json")
    if identity["experiment"] != source_pins(read(job)) or pin(job) != identity["paired_binding_sha256"]:
        raise ValueError("The frozen adaptive trial launch binding changed")
    target = root/"candidate"
    original = raw_cfo_north_trial.publish_saved

    def research(request, output, *args, **kwargs):
        if output != target:
            raise ValueError("The adaptive sink may only publish this new research result")
        with research_layout(output):
            return original(request, output, *args, **kwargs)

    with patch.object(raw_cfo_north_trial, "publish_saved", research):
        dense_hybrid_combined.worker(job, target)


def launch(root):
    from aperture_trial import RELEASE
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    if root.parent.resolve(strict=True) != Path("/dev/shm") or root.exists():
        raise ValueError("Use a new private tmpfs result")
    machine = host()
    original = read(CONTROL/"result.json")
    job = CONTROL/"binding.json"
    if (original["state"] != "complete" or not all(original["active"].values())
            or original["binding_sha256"] != pin(job) or original["clock"]["exit_code"]):
        raise ValueError("Requires the checked complete portable plus Cairo paired reference")
    sources = source_pins(read(job))
    root.mkdir()
    (root/"tmp").mkdir()
    (root/"fonts").mkdir()
    for file in (CONTROL/"fonts").glob("fontlist-*.json"):
        (root/"fonts"/file.name).hardlink_to(file)
    (root/"binding.json").write_bytes(job.read_bytes())
    command = ["/usr/bin/timeout", "--kill-after=2s", "100s", RELEASE/"venv/bin/python", "-IB",
               Path(__file__), "worker", root]
    write(root/"research-binding.json", dict(experiment=sources, paired_binding_sha256=pin(job),
          paired_result_sha256=pin(CONTROL/"result.json"), machine=machine, command=list(map(str, command))))
    env = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    clock = measure(command, env, root/"candidate")
    write(root/"clock.json", clock)


def medium_pins():
    if any(pin(MEDIUM_CONTROL/name) != value for name, value in MEDIUM_PINS.items()):
        raise ValueError("The exact independent archived medium control changed")
    runner = MEDIUM_SOURCE/"catalogue_block_portable_0316.py"
    return {p.name: pin(p) for p in (*EXPERIMENT, MEDIUM_PROTOCOL, runner)}


def medium_worker(root):
    from catalogue_block_portable_0316 import worker as archived
    from reports.ALGO08.v3.live_adaptive_grid_entry import research_layout
    import unified_short_bootstrap

    if read(root/"research-binding.json")["experiment"] != medium_pins():
        raise ValueError("The frozen medium adaptive launch binding changed")
    original = unified_short_bootstrap.publish_active

    def research(opts, *args, **kwargs):
        if opts.output != root/"portable":
            raise ValueError("Adaptive transfer may publish only its own research result")
        with research_layout(opts.output):
            return original(opts, *args, **kwargs)

    with patch.object(unified_short_bootstrap, "publish_active", research):
        archived(root)


def medium_launch(root):
    from portable_orbit_index_trial import local_launcher_tools

    local_launcher_tools()
    from aperture_trial import RELEASE
    from dense_geographic_trial import host
    from full_short_physical import environment
    from portable_orbit_0316_repair import admitted
    from short_raw_diagnostic import measure

    if root.parent.resolve(strict=True) != Path("/dev/shm") or root.exists():
        raise ValueError("Use a new private tmpfs result")
    sources = medium_pins()
    named = read(MEDIUM_CONTROL/"portable/saved-0316-worker.json")
    if named["native_sha256"] != MEDIUM_NATIVE or named["receipt"]["decision"] != "complete":
        raise ValueError("The archived medium publication is not the enrolled completed native packet")
    admitted()
    machine = host()
    root.mkdir(mode=0o700)
    (root/"tmp").mkdir()
    (root/"fonts").mkdir()
    for file in (MEDIUM_CONTROL/"fonts").glob("fontlist-*.json"):
        (root/"fonts"/file.name).write_bytes(file.read_bytes())
    command = ["/usr/bin/timeout", "--kill-after=2s", "60s", RELEASE/"venv/bin/python", "-IB",
               Path(__file__), "medium-worker", root]
    write(root/"research-binding.json", dict(experiment=sources, paired_binding_sha256=MEDIUM_PINS["portable/saved-0316-worker.json"],
          paired_result_sha256=MEDIUM_PINS["combined-verified.json"], machine=machine, command=list(map(str, command))))
    env = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    write(root/"portable.clock.json", measure(command, env, root/"portable"))


def medium_checks(control, root, old, new):
    from catalogue_block_portable_0316 import exact_rank
    from portable_orbit_0316_repair import regional_evidence

    prior, current = (read(p/"portable-preparation.json") for p in (control, root))
    if (current["loading"]["fallback"] or current["index_sha256"] != prior["index_sha256"]
            or current["fingerprint"] != prior["fingerprint"] or regional_evidence(old) != regional_evidence(new)):
        raise ValueError("The archived medium source, preparation or regional result changed")
    exact_rank(read(root/"rank.json"))
    return [read(p/"portable/final-fit-options.json")["named_survivor_finish"] for p in (control, root)]


def dense_checks(control, root, workers):
    old_activation, new_activation = (read(r/"candidate/combined-activation.json") for r in (control, root))
    if (old_activation["rank_status"] != new_activation["rank_status"] or old_activation["rank_status"] != "compacted"
            or any(a["compatibility"]["fallback"] or a["loading"]["fallback"] for a in new_activation["orbit"]["transfers"])):
        raise ValueError("The matched adaptive run did not use the same portable and compact rank path")
    return [w["named_survivor_finish"] for w in workers]


def score(root, *, medium=False):
    from joint_publication import figure_evidence
    from leo.contracts.digests import canonical_digest, sha256_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from reports.ALGO08.v3.live_adaptive_grid import quality
    from reports.ALGO08.v3.live_adaptive_grid_entry import NAMESPACE, read_manifest, read_sidecar, research_folder

    enrollment = read(root/"research-binding.json")
    control, leaf, native = (MEDIUM_CONTROL, "portable", MEDIUM_NATIVE) if medium else (CONTROL, "candidate", NATIVE)
    clock_name, worker_name = (("portable.clock.json", "saved-0316-worker.json") if medium
                               else ("clock.json", "dense-hybrid-combined-worker.json"))
    paired = "combined-verified.json" if medium else "result.json"
    if enrollment["paired_result_sha256"] != pin(control/paired):
        raise ValueError("The independently sealed paired full-layout reference changed")
    reference_clock, candidate_clock = (read(r/clock_name) for r in (control, root))
    if candidate_clock["exit_code"] or reference_clock["exit_code"]:
        raise ValueError("Both paid workers must exit successfully")
    c, a = control/leaf, root/leaf
    old_worker, new_worker = (read(r/worker_name) for r in (c, a))
    old, new = (read(r/"joint-research-receipt.json") for r in (c, a))
    finishes = medium_checks(control, root, old, new) if medium else dense_checks(control, root, (old_worker, new_worker))
    detector_field = "detector" if medium else "detector_recipe_sha256"
    png = (read(a/"final-fit-options.json")["png_readback"] if medium else new_worker["png"])
    receipt = old_worker["receipt"]
    run = receipt["run_id"]
    terminal = [read(r/"fast-scan-automatic-work"/run/"terminal.json") for r in (c, a)]
    terminal_same = terminal[0] == terminal[1] and canonical_digest(terminal[0]) == receipt["terminal_sha256"]
    if (not terminal_same or any(new_worker["receipt"][k] != receipt[k] for k in RECEIPT_SCIENCE) or receipt["decision"] != "complete"
            or old_worker["native_sha256"] != native or new_worker["native_sha256"] != native
            or old_worker[detector_field] != new_worker[detector_field]
            or not all(worker["handoffs"] == 1 and (worker["no_waveform"] if medium else
                not worker["waveform_calls"] and worker["staged_inventory"]) for worker in (old_worker, new_worker))
            or old["selected_rows"] != new["selected_rows"] or old["solve"]["objective_replay"] != new["solve"]["objective_replay"]
            or not finishes[1]["paid_final_fit"] or finishes[0] != finishes[1]
            or png["verified"] != 8 or png["reused"] != 8 or png["fallbacks"]):
        raise ValueError("Decisions, fit, owner rows or matched active pipeline changed")
    before_store = FastStandardAnalysisStore(c)
    full, full_path = before_store.position_grid(run), before_store.position_path(run)
    current = read_manifest(a, run)
    adaptive, path = (read_sidecar(a, run, name) for name in ("sample", "path"))
    expected_calls = [2*grid["evaluated_points"]-2 for grid in (full, adaptive)]
    for trace, count in zip((old, new), expected_calls, strict=True):
        handoff = trace["receipt"]["posterior_grid_handoff"]
        if handoff["factor_calls"] != count or handoff["prediction_calls"] != count:
            raise ValueError("Expected the same native posterior grid handoff at every paid non-endpoint score")
    plots = current["publication"]["artifacts"]
    folder = research_folder(a, run)
    if (a/"fast-scan-standard-v2").exists() or current["kind"] != NAMESPACE:
        raise ValueError("Adaptive output entered the released version-3 namespace")
    for row in (full_path, path):
        row["binding"].pop("position_png_sha256")
    if (full_path != path or adaptive["endpoints"] != full["endpoints"]
            or adaptive["endpoint_latlon"] != full["endpoint_latlon"] or adaptive["region_center"] != full["region_center"]
            or adaptive["binding"]["terminal_sha256"] != receipt["terminal_sha256"]):
        raise ValueError("History, matched endpoints, terminal or geographic frame changed")
    image_scores = {}
    for entry in plots:
        name, digest = entry["name"], entry["sha256"]
        data = (folder/(digest[7:]+".png")).read_bytes()
        observed = figure_evidence(data, sha256_digest(data))
        expected = old["evidence"]["images"][name]
        if (observed["sha256"] != digest or observed["size"] != tuple(expected["size"])
                or (name != "position" and (digest != expected["sha256"] or observed["rgba_sha256"] != expected["rgba_sha256"]))):
            raise ValueError(f"Unexpected research image change in {name}")
        image_scores[name] = dict(rgba_unchanged=observed["rgba_sha256"] == expected["rgba_sha256"],
                                  png_unchanged=digest == expected["sha256"], **observed)
    audit = quality(adaptive, full)
    summary = dict(reference_layout=adaptive["reference_layout"], initial_layout=adaptive["initial_layout"],
                   evaluated_points=adaptive["evaluated_points"], actual_calls=adaptive["objective_calls"],
                   sample_cpu_s=adaptive["sample_cpu_s"], elapsed_seconds=adaptive["elapsed_seconds"],
                   refinement_cpu_s=adaptive["refinement_cpu_s"], full_grid_elapsed_s=full["elapsed_seconds"],
                   audit=audit, images=image_scores, phase_state_sha256=adaptive["phase_state_sha256"],
                   paired_binding=enrollment["paired_binding_sha256"], sample_sha256=current["sidecars_sha256"]["sample"],
                   arms=current["publication"]["arms"], terminal_sha256=receipt["terminal_sha256"],
                   original_owner_rows_sha256=canonical_digest(new["selected_rows"]))
    return dict(layout=summary, match=terminal_same, original_waveform_reads=0, scorer_sha256=pin(Path(__file__)),
                native_posterior_evaluations=expected_calls,
                clocks=dict(reference=reference_clock, adaptive=candidate_clock,
                            old_solve=old["solve"], new_solve=new["solve"],
                            old_evidence=old["route_details"]["standard_evidence_clocks"],
                            new_evidence=new["route_details"]["standard_evidence_clocks"],
                            old_render=old_worker["layout"]["render"], new_render=new_worker["layout"]["render"],
                            saved_elapsed_s=reference_clock["elapsed_s"]-candidate_clock["elapsed_s"]),
                passed=bool(audit["passed"] and reference_clock["elapsed_s"]-candidate_clock["elapsed_s"]>1.))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker", "verify", "medium-launch", "medium-worker", "medium-verify"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    medium = args.action.startswith("medium-")
    if medium:
        sys.path.insert(0, str(MEDIUM_SOURCE))
    if args.action.endswith("verify"):
        write(args.root/"result.json", score(args.root, medium=medium))
    else:
        {"launch": launch, "worker": worker, "medium-launch": medium_launch, "medium-worker": medium_worker}[args.action](args.root)
