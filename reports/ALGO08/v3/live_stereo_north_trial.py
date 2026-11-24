"""Compare the live schedule on the original resident North containing offer."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy
import subprocess
import sys


HERE = Path(__file__).resolve().parent
PREFIX = Path("/dev/shm/leo-live-stereo-member.mCYu3fhw/pair/result.json")
PREFIX_SHA = "13b11c5ef5cb2c2c9619ad1f0a5fd1ddf553642a3784cb7095ff59b8deb8cafa"
WEAK = Path("/dev/shm/leo-v3-whole-stereo-blocks-weak01/score.json")
WEAK_SHA = "fb4a679f1f02356f04a962ac488c9c733dac4fb7247bbd6fdb60170a3ff35944"
ORDER = ("unmasked", "masked")


def run(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from full_short_physical import CACHE_LIB, CACHE_SHA, environment
    from joint_held_north_raw import cache_snapshot_for_run, references, tmpfs, validate_workload
    from leo.storage.fast_scan import FastScanStore
    from raw_cfo_north_trial import CURVATURE_FLAGS, PUBLICATION_FLAGS, workload
    from short_raw_diagnostic import measure
    from tools.pipeline_eval.qualification.cache_residency import load_query
    from tools.pipeline_eval.qualification.paired_publication import NAMED_V3, verified_v3

    prefix = json.loads(checked(PREFIX, PREFIX_SHA))
    weak = json.loads(checked(WEAK, WEAK_SHA))
    if not weak["quality_vs_named"] or prefix["frozen"]["skipped_native_lanes"] != {"short_primary": 28}:
        raise ValueError("Original weak qualifications are required")
    machine = host()
    request, manifests = workload(root)
    reference, results = references()
    validate_workload(request, reference["assignment"], machine, reference["machine"])
    for path in (root.parent, request["recording"], request["inside_offer"], request["archive"]["root"]):
        tmpfs(path)
    stock = verified_v3(NAMED_V3)
    original = json.loads(checked(Path("/dev/shm/leo-v3-combined-raw-north-result01/binding.json"),
                                  "da2d6859a2d01ce852a41ba1b637fc334df9a28f523ed6583fdf313564082bed"))
    flags = []
    for flag, pin in original["libraries"].items():
        checked(Path(pin["path"]), pin["sha256"])
        flags.extend((flag, pin["path"]))
    checked(CACHE_LIB, CACHE_SHA)
    query = load_query(CACHE_LIB)
    root.mkdir()
    for name in ("tmp", "fonts"):
        (root / name).mkdir()
    env = environment(root)
    env.update(TMPDIR=str(root / "tmp"), XDG_CACHE_HOME=str(root / "tmp"))
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=25)
    store = FastScanStore(root)
    common = ["/usr/bin/timeout", "--kill-after=2s", "45s", python, "-IB", HERE / "unified_short_bootstrap.py",
              "--recording", request["recording"], "--archive", request["archive"]["root"], "--region", request["inside_offer"],
              *flags, *CURVATURE_FLAGS, *PUBLICATION_FLAGS]
    commands = {mode: list(map(str, [*common, "--output", root / mode, *(() if mode == "unmasked" else ("--whole-stereo-blocks",))]))
                for mode in ORDER}
    write(root / "binding.json", dict(request=request, commanded=commands, order=ORDER, installed=stock,
          source_sha256={name: sha256((HERE / name).read_bytes()).hexdigest()
             for name in ("live_stereo_blocks.py", "unified_short_bootstrap.py", "live-stereo-blocks-protocol.md", Path(__file__).name)},
          weak_score_sha256=WEAK_SHA, member_verified_sha256=PREFIX_SHA, machine=machine))
    run_clocks = {}
    for mode in ORDER:
        before = cache_snapshot_for_run(store, request, manifests, query)
        measured = measure(commands[mode], env, root / mode)
        write(root / f"{mode}-clock.json", dict(clock=measured, before=before))
        after = cache_snapshot_for_run(store, request, manifests, query)
        run_clocks[mode] = dict(clock=measured, before=before, after=after)
        write(root / f"{mode}-admission.json", run_clocks[mode])
        if measured["exit_code"]:
            raise ValueError(measured["stderr_tail"])
    score(root, request, results["stock"], run_clocks)


def score(root, request, stock, clocks):
    from aperture_trial import read, write
    from empty_bootstrap import checked
    from joint_held_north_raw import EXACT_PACKETS, REFERENCE
    from joint_publication import artifacts
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from live_stereo_blocks import PLANNER_SHA
    from live_stereo_member_trial import PLANNER
    from north_interlaced_raw import TRUTH_SHA
    from raw_cfo_north_trial import native_file
    from tools.pipeline_eval.qualification.paired_publication import evidence
    from tools.pipeline_eval.scoring import distance_km

    truth_bytes = subprocess.check_output(["git", "-C", str(HERE.parents[2]), "show", "HEAD:reports/ALGO08/regional-release/scoring-key.json"])
    if sha256(truth_bytes).hexdigest() != TRUTH_SHA:
        raise ValueError("Original independent survey source changed")
    (truth,) = {tuple(row["truth"]) for row in json.loads(truth_bytes)["answers"].values()
                if row["recording"] == Path(request["recording"]).name}
    packets, out = {}, {}
    for mode in ("stock", *ORDER):
        path = (REFERENCE if mode == "stock" else root) / mode
        bootstrap = read(path / "unified-short-bootstrap.json") if mode != "stock" else None
        receipt = bootstrap["receipt"] if bootstrap else stock["verified"]["receipt"]
        clock = clocks[mode]["clock"] if mode != "stock" else stock["clock"]
        val = evidence(path, receipt, clock["started_unix_ns"], read_only=True)
        if val["raw_authority"] != request["authority"] or receipt["region"] != stock["verified"]["receipt"]["region"]:
            raise ValueError("Original region or authority differs between arms")
        images = artifacts(path, receipt)
        store = FastStandardAnalysisStore(path)
        grid = store.position_grid(receipt["run_id"])
        standard_path = store.position_path(receipt["run_id"])
        if grid is not None and (not grid["complete"] or not grid["matched_c_grid"] or len(images["images"]) != 8
            or any(doc["binding"]["position_png_sha256"] != images["images"]["position"]["sha256"] for doc in (grid, standard_path))):
            raise ValueError("Missing checked evidence for both calibration arms")
        arms = {arm: dict(value, error_m=None if value["latlon"] is None else 1000*distance_km(truth, value["latlon"]))
                for arm, value in val["arms"].items()}
        publish = path / "joint-research-receipt.json"
        research = read(publish) if publish.exists() else {}
        out[mode] = dict(through_exit=clock, arms=arms, figures=images, receipt=receipt, owners=val["owners"],
                         grid_points=0 if grid is None else grid["evaluated_points"], ordered_rows=research.get("selected_rows"),
                         acquisition=None if bootstrap is None else bootstrap["receiver_audit"],
                         phases=None if bootstrap is None else bootstrap["phases"], solve=research.get("solve"))
        if bootstrap is not None:
            if (bootstrap["raw_acquisitions"] != 1 or bootstrap["verified_handoffs"] != 1
                    or bootstrap["causal_cutoff_utc_ns"] != request["cutoff_utc_ns"]
                    or receipt["window_count"] != request["issued"] or bootstrap.get("held_anchor_route")
                    or "fixed_epoch_cfo_refinement" in bootstrap["receiver_recipe"]):
                raise ValueError("Held worker changed the original unfiltered receiver or signed scope")
            packets[mode] = json.loads(checked(native_file(path), bootstrap["native_sha256"][7:]))
    parent, masked = (packets[mode] for mode in ORDER)
    checked(PLANNER, PLANNER_SHA)
    planner = runpy.run_path(str(PLANNER))
    original = json.loads(checked(native_file(EXACT_PACKETS[0][0]), EXACT_PACKETS[0][1]))
    projected, audit = planner["project"](parent, planner["schedule"](parent))
    expected = projected["source"]["probes"] == masked["source"]["probes"]
    if not expected or out["masked"]["acquisition"]["native"]["native_calls"] != audit["kept_native_lanes"]:
        raise ValueError("The held live skip differs from the frozen unfiltered schedule")
    write(root / "result.json", dict(runs=out, cache=clocks, scope="original North simulation containing", named_historical=True,
          exact_offline_subset=expected, native_archived_unmasked_match=parent["source"]["probes"] == original["source"]["probes"],
          mask=audit, history=planner["exposure"](parent, masked, set(audit["skipped_visits"])), scoring_key_sha256=TRUTH_SHA))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    run(parser.parse_args().root)
