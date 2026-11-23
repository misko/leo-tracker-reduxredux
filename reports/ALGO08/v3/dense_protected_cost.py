"""Time and score one frozen saved dense publication with protected local repair."""

import argparse
from math import isclose
from pathlib import Path
import subprocess
from time import perf_counter

from aperture_trial import RELEASE, archive_identity, read, write
from dense_full_short_raw import checked, usage
from dense_geographic_trial import host
from full_short_physical import environment


HERE = Path(__file__).resolve().parent
DATA = HERE / "measurements"
SOURCE = Path("/var/tmp/leo-v3-regional-dense-pair")
STOCK_ROOT = Path("/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/v3-bounds-DS30-0008-pair/baseline")
BINDING_PIN = "2d93dd6db50e0ff697fbfc33d69ebaceb0475a2ebf3296e7368a30e8c551d3cb"
UNFILTERED_PIN = "11c554cbcca4f756e07e810bbc7b34b548a799fd005645fd4d9e5fcbba8ef72e"
STOCK_PIN = "0d2ec8bfd30a71142c9f88dcbcf2bcdef0d5f4188e8f6b42cb280bdaa06b6312"
SOURCE_PIN = "sha256:ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85"
WORKER_FILES = {
    "local_future_repair_trial.py": "873612d549e1deef09fd6561cce0b8c79e791dcdda1138eb5eaf382d1ec47cc0",
    "local_future_inputs.py": "6283ef3c7643276cf83703209f73bf9e5c2a2b39f4bd41ed4812e11a081c22c4",
    "local_future_repair.py": "2c22d0badf4431e8ef7f914d1b65d80bfd96344dc8b9b52ed0c9687ee8150fbe",
    "local-future-repair-protocol.md": "34d8a3121846bd0d9e01e2ad88913313ceabd26046c6a4ccf322607a65095bde",
    "joint_publication.py": "dfbf0024b6055d2eae3c77eabcaf1f09c79653bded96bdb7b362f89f8fd245fa",
    "blind_joint_route.py": "f7a66aea7ed875f5de067a0125948cd51c91e329ac0ea4b4ab1b4da6db5d1ca6",
}
FORWARD_PIN = "2e974f0869f6edee312cd415fd61c16ee0a0caea2f9363f56ad43a84b8a65978"
MODEL_PINS = {
    "acquisition-throughput.json": "fc46925e68437054169e2a3008388493554baf5c92f495eb3beb9434c10e620a",
    "regional-dense-budget.json": "20ca6db13e6294d34ae732635158aef332f622127d120d6f6ca1229082e78677",
    "regional-dense-pair.json": "7ab29f3551ec8e237dd74d38fdab05ad4cb4750d7ae6b67560cc206c99e94749",
}


def inputs():
    pair = read(checked(DATA / "bounds-DS30-0008-pair.json", STOCK_PIN))
    binding = read(checked(SOURCE / "binding.json", BINDING_PIN))
    unfiltered = read(checked(SOURCE / "native/joint-research-receipt.json", UNFILTERED_PIN))
    packet, = (SOURCE / "native/fast-scan-automatic-work").glob("*/detections.json")
    checked(packet, SOURCE_PIN)
    region = checked(Path(pair["region_file"]), pair["region_file_sha256"])
    archive = Path(binding["archive"]["root"])
    if (pair["case"] != "DS30-0008" or archive_identity(archive) != binding["archive"]
            or binding["archive"] != pair["archive"] or read(region) != binding["offer"]
            or binding["packet_sha256"] != SOURCE_PIN or unfiltered["saved_digest"] != SOURCE_PIN
            or unfiltered["receipt"]["session_id"] != pair["runs"]["baseline"]["receipt"]["session_id"]):
        raise ValueError("Unexpected original recording, TLE archive, short input or region")
    return pair, binding, unfiltered, packet, region, archive


def run(root, geo, regional):
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA

    machine = host()
    if subprocess.check_output(["findmnt", "-T", str(root.parent), "-no", "FSTYPE"], text=True).strip() != "tmpfs":
        raise ValueError("Use a fresh tmpfs output")
    pair, binding, _, packet, region, archive = inputs()
    for name, digest in WORKER_FILES.items():
        checked(HERE / name, digest)
    checked(HERE / "north_factor_swap.py", FORWARD_PIN)
    checked(geo, GEOGRAPHIC_SHA)
    checked(regional, TRACK_SCORES_SHA)
    root.mkdir()
    env = environment(root)
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   check=True, env=env, timeout=30)
    command = [python, "-BPs", HERE / "local_future_repair_trial.py", "worker", packet, SOURCE_PIN,
               root / "repair", pair["recording"], archive, region, geo, regional]
    write(root / "binding.json", dict(native_sha256=SOURCE_PIN, stock_pair_sha256=STOCK_PIN,
          unfiltered_receipt_sha256=UNFILTERED_PIN, bound_native_sha256=BINDING_PIN, archive=binding["archive"],
          offer=binding["offer"], library_sha256=dict(geographic=GEOGRAPHIC_SHA, regional=TRACK_SCORES_SHA),
          forward_source_sha256=FORWARD_PIN, command=list(map(str, command)), worker_sources=WORKER_FILES))
    print("Timing the pinned DS30-0008 protected saved worker", flush=True)
    start, before = perf_counter(), usage()
    try:
        result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=150)
        status, error = result.returncode, result.stderr
    except subprocess.TimeoutExpired as exc:
        status, error = 124, str(exc)
    wall, after = perf_counter() - start, usage()
    write(root / "process.json", dict(elapsed_s=wall, exit_code=status, machine=machine,
          **{k: after[k] - before[k] for k in before}))
    (root / "worker.stderr").write_text(error)
    if status:
        raise RuntimeError(f"Protected worker exited {status}. {error[-3500:]}")


def timing_models(solve, baseline, inventory):
    from acquisition_throughput import gates, minimum_rate
    from regional_dense_budget import select

    common, reference = baseline["common_charge_s"], baseline["historical_installed_solve_cpu_s"]
    if reference <= 0 or solve <= 0:
        raise ValueError("Expected positive solver CPU clocks")
    result = {}
    for count in ("4", "16"):
        roster = baseline["panels"][count]
        rows = select(inventory, roster["cases"])
        scenarios = {}
        for scenario in ("observed_dense", "fastest_prefix"):
            old = roster["scenarios"][scenario]
            rate = old["reader_MB_s"]
            base = gates(rows, rate, baseline["solve_cpu_s"] / reference, startup_s=common)
            if not all(isclose(a, b, abs_tol=1e-12) for a, b in zip(base, (old["median_ratio"], old["summed_ratio"]), strict=True)):
                raise ValueError("Model no longer reproduces the archived elapsed ratios")
            median, summed = gates(rows, rate, solve/reference, startup_s=common)
            target = gates(rows, rate, 16./reference, startup_s=common)
            scenarios[scenario] = dict(reader_MB_s=rate, old_unfiltered_ratio=list(base), protected_ratio=[median, summed],
                ratio_with_16_s_solve=list(target), dense_solve_budget_s=old["dense_solve_budget_s"],
                both_halved=median <= .5 and summed <= .5)
        result[count] = dict(cases=roster["cases"], unchanged_outcomes=roster["unchanged_outcomes"], scenarios=scenarios,
            minimum_reader_rate_MB_s=[minimum_rate(rows, solve/reference, k, startup_s=common) for k in (0, 1)])
    return dict(panels=result, dense_solve_cpu_s=solve, gap_to_16_cpu_s=solve-16., old_solver_cpu_s=baseline["solve_cpu_s"],
                stock_clock_cpu_s=reference, common_charge_s=common, input_pins=MODEL_PINS)


def clock_buckets(trial, policy):
    route = trial["route_details"] or {}
    repair = route.get("local_future_repair", {})

    def clocks(source, key):
        return source.get(key, {}).get("cpu_s", 0.0)

    charged = dict(forward_selection=clocks(policy, "selection"), early_region=sum(row["cpu_s"] for row in trial["early_regional"]),
                   candidate_before_evidence=clocks(route, "candidate_pre_evidence_clocks"),
                   signed=clocks(route, "signed_total_clocks"), exterior=clocks(route, "exterior_clocks"),
                   protected_repair=clocks(repair, "cost"), protected_exterior=clocks(repair, "exterior_clocks"),
                   standard_evidence=clocks(route, "standard_evidence_clocks"), fallback=clocks(route, "fallback_clocks"))
    buckets = dict(charged, solve_other=trial["solve"]["cpu_s"] - sum(charged.values()))
    if buckets["solve_other"] < 0.:
        raise ValueError("Stage clocks unexpectedly overlap")
    return buckets


def score(root, output):
    from joint_publication import artifacts
    from local_future_0057 import changes
    from local_future_inputs import future_observations
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from mixture_score import ARMS, section
    from north_factor_swap import continued
    from tools.pipeline_eval.qualification.paired_publication import verify_v3_publication
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    original, binding, unfiltered, source, _, _ = inputs()
    sealed = read(root / "binding.json")
    clock = read(root / "process.json")
    if (clock["exit_code"] != 0 or sealed["native_sha256"] != SOURCE_PIN or sealed["worker_sources"] != WORKER_FILES
            or sealed["archive"] != binding["archive"] or sealed["offer"] != binding["offer"]
            or sealed["forward_source_sha256"] != FORWARD_PIN):
        raise ValueError("The publication was not produced by the frozen dense launch")
    root = root / "repair"
    trial = read(root / "joint-research-receipt.json")
    policy = read(root / "local-future-policy.json")
    receipt = trial["receipt"]
    saved, = (root / "fast-scan-automatic-work").glob("*/detections.json")
    terminal_path = saved.parent.parent / receipt["run_id"] / "terminal.json"
    terminal = read(terminal_path)
    stock = original["runs"]["baseline"]
    stock_receipt = stock["receipt"]
    verify_v3_publication(STOCK_ROOT, stock_receipt)
    stock_terminal = read(STOCK_ROOT / "fast-scan-automatic-work" / stock_receipt["run_id"] / "terminal.json")
    control = SOURCE / "native"
    before_terminal = read(control / "fast-scan-automatic-work" / unfiltered["receipt"]["run_id"] / "terminal.json")
    evidence = artifacts(root, receipt)
    if (canonical_digest(stock_terminal) != stock_receipt["terminal_sha256"] or stock_terminal["arms"] != stock["arms"]
            or canonical_digest(terminal) != receipt["terminal_sha256"]
            or canonical_digest(before_terminal) != unfiltered["receipt"]["terminal_sha256"]
            or terminal["region"] != stock_terminal["region"] or terminal["region"] != before_terminal["region"]
            or terminal["native_sha256"] != SOURCE_PIN or before_terminal["native_sha256"] != SOURCE_PIN
            or canonical_digest(read(saved)) != SOURCE_PIN or policy["native_sha256"] != SOURCE_PIN
            or trial["saved_digest"] != SOURCE_PIN or policy["implementation"] != WORKER_FILES
            or canonical_digest(evidence) != canonical_digest(trial["evidence"])
            or receipt["counts"] != unfiltered["receipt"]["counts"]
            or receipt["session_id"] != stock_receipt["session_id"]):
        raise ValueError("A saved input, named installed terminal, publication, or local policy lost its original binding")
    route = trial["route_details"] or {}
    repair = route.get("local_future_repair", {})
    native = read(source)
    forward = continued(native)
    future_ids = [row["observation_id"] for row in future_observations(native, forward)]
    if canonical_digest(forward) != policy["forward_sha256"] or future_ids != policy["future_ids"]:
        raise ValueError("Forward or future roster differs from the frozen worker policy")
    differences, images = {}, {}
    if receipt["decision"] == "complete":
        store = FastStandardAnalysisStore(root)
        published = store.detail(receipt["run_id"])
        if (published["raw_authority"] != stock["raw_authority"] or not trial["solve"]["grid_complete"]
                or trial["solve"]["objective_replay"] != dict.fromkeys(ARMS, 0.0)):
            raise ValueError("Incomplete or unbound dense output evidence")
        for arm in ARMS:
            rows = trial["selected_rows"][arm]
            differences[arm] = changes(unfiltered["selected_rows"][arm], rows)
            observed = {oid: (owner, role) for oid, owner, role in rows}
            additions = repair.get("added", []) if repair.get("decision") == "accepted" else []
            if (not {row["observation_id"] for row in additions} <= set(policy["future_ids"])
                    or any(observed.get(row["observation_id"]) != (row["norad"], row["role"]) for row in additions)):
                raise ValueError("A recorded repair point lacks its expected final owner or role")
        for image, found in evidence["images"].items():
            images[image] = dict(file_equal_to_installed=found["sha256"] == stock["witnesses"]["pngs"][image],
                pixels_equal_to_installed=found["rgba_sha256"] == stock["witnesses"]["png_pixels"][image]["rgba_sha256"],
                file_equal_to_unfiltered=found["sha256"] == unfiltered["evidence"]["images"][image]["sha256"],
                pixels_equal_to_unfiltered=found["rgba_sha256"] == unfiltered["evidence"]["images"][image]["rgba_sha256"])
    ref, = [row["reference"] for row in read(checked(REFERENCE, REFERENCE_SHA256))["cases"]
            if row["dataset_label"] == "DS30-0008" and row["authority_eligible"] and row["sealed_metadata_digests_verified"]]
    truth = [ref["latitude_deg"], ref["longitude_deg"]]
    science = dict(named_installed=section(stock_terminal["arms"], truth, stock_terminal["arms"]),
                   unfiltered=section(before_terminal["arms"], truth, stock_terminal["arms"]),
                   protected=section(terminal["arms"], truth, stock_terminal["arms"]),
                   protected_vs_unfiltered=section(terminal["arms"], truth, before_terminal["arms"]))
    controls = {name: read(checked(DATA / name, pin)) for name, pin in MODEL_PINS.items()}
    old = controls["regional-dense-pair.json"]["runs"]["native"]
    model = timing_models(trial["solve"]["cpu_s"], controls["regional-dense-budget.json"],
                          controls["acquisition-throughput.json"]["rows"])
    write(output, dict(case="DS30-0008", output_root=str(root), binding=sealed, process=clock, solve=trial["solve"],
        publication_cpu_s=trial["publication_cpu_s"], publication_elapsed_s=trial["publication_elapsed_s"],
        terminal=terminal, terminal_sha256=receipt["terminal_sha256"], retained_native_sha256=SOURCE_PIN,
        prior_terminal_pins=dict(named_installed=stock_receipt["terminal_sha256"], unfiltered=unfiltered["receipt"]["terminal_sha256"]),
        science=science, evidence=evidence, image_comparisons=images, owner_changes_vs_unfiltered=differences,
        quality_passed=receipt["decision"] == "complete" and all(
            row["delta_error_km"] <= 0.25 for row in science["protected"]["arms"].values()),
        forward=dict(sha256=policy["forward_sha256"], future_opportunities=len(future_ids), selection=policy["selection"],
                     original_selections=sum(bool(row["candidates"]) for row in native["source"]["probes"]),
                     selected=sum(bool(row["candidates"]) for row in forward["source"]["probes"])),
        route=trial["route"], route_stage_clocks={key: value for key, value in route.items() if key.endswith("_clocks")},
        early_regional=trial["early_regional"], cold=route.get("cold"), finish=route.get("finish"),
        signed=route.get("signed"), initial_pair_passed=route.get("pair_passes"), ordinary_retry=route.get("repair"),
        warm_signed_fit=route.get("warm_signed_fit"), salvage_counters=route.get("certified_salvage"),
        repair=repair, fallback_reason=route.get("reason"), selected_roles=trial["selected_roles"],
        charged_solver_cpu_s=clock_buckets(trial, policy), models=model, archived_unfiltered_cpu_s=old["solve_cpu_s"]))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    modes = cli.add_subparsers(dest="mode", required=True)
    launch = modes.add_parser("run")
    for name in ("root", "geo", "regional"):
        launch.add_argument(name, type=Path)
    scorer = modes.add_parser("score")
    scorer.add_argument("root", type=Path)
    scorer.add_argument("output", type=Path)
    arguments = vars(cli.parse_args())
    mode = arguments.pop("mode")
    {"run": run, "score": score}[mode](**arguments)
