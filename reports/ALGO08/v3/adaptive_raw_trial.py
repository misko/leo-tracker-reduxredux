"""Run the predeclared page-resident North adaptive map, then screen South."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys


HERE = Path(__file__).resolve().parent
CHECKOUT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.append(str(CHECKOUT))

from aperture_trial import read, write
from empty_bootstrap import checked


FLAG = "--research-adaptive-position-map"
CONTROLS = {
    "north": (Path("/dev/shm/leo-v3-eight-ms-native-north02"), {
        "binding.json": "42a25801481957228420dc9acd501c8beb4e2bb084578d7959219a8cdf8daed4",
        "science-seal.json": "74f85ba14d14e085ea0832933acd3ad1fed001d6b0d698d2c05b52a39a77a849",
        "containing/joint-research-receipt.json": "f0990c1e5a60bc2f6fb05973529e4aeb6bc570a673186a52235aebb66f37e909",
    }),
    "south": (Path("/dev/shm/leo-v3-eight-ms-south-result01"), {
        "binding.json": "c68bb6474204d10365a3080dcf55e95c4864bcc7ff7503e459dadddb8809bf9c",
        "seal.json": "b1dbe1ee71fb7dcb63ced474b7aa13e7877db2a801149899de3b3c4da17581fc",
        "containing/joint-research-receipt.json": "b3f10523639ef92b85055b16cf95b75b6a83ffef605811c4e0bcf419f470709b",
    }),
}
ADAPTER = {
    "adaptive_grid_screen.py": "5e24ed9bbc6a435dea376dc4029c571f83d2b21fd14c92749deb748f341307db",
    "live_adaptive_grid.py": "b555d640153b896c2261c024d0f7a8695135a7b7bf0c63acf6a5bf9d8e07319d",
    "live_adaptive_grid_entry.py": "da1c432809071e77af94c854fdcd323f8e6dfda0b34a9db8c4830763fc643335",
}
SCIENCE = ("run_id", "session_id", "window_count", "counts", "region", "decision", "terminal_sha256")
RAW_IDENTITY = ("route", "archive_root", "requested_offer_sha256", "frozen_specification", "clock_anchor",
                "causal_cutoff_utc_ns", "native_sha256", "receiver_recipe", "detector_recipe_sha256",
                "held_anchor_route", "graph_proof", "raw_acquisitions", "verified_handoffs")
SOUTH_WALL_GATE_S = 0.20


def control(case):
    root, pins = CONTROLS[case]
    binding, sealed, research = [json.loads(checked(root / name, pin)) for name, pin in pins.items()]
    if sealed["clock"]["exit_code"] or sealed["raw"]["receipt"]["decision"] != "complete":
        raise ValueError("The enrolled full-layout reference must be a completed raw publication")
    return root, binding, sealed, research


def adaptive_command(original, output):
    command = list(original)
    required = ("--eight-ms-native-history", "--catalogue-block-rank", "--portable-orbit-index",
                "--grid-feature-projection-library", "--one-pass-web-png", "--named-survivor-finish",
                "--direct-orbit-figures", "--direct-residual-figures")
    incompatible = (FLAG, "--full-anchor-primary-library", "--whole-stereo-blocks", "--short-lane-mask",
                    "--anchored-cfo-pack", "--select-before-cfo", "--packed-ci16-map")
    if (Path(command[5]).name != "combined_raw_research.py" or any(flag not in command for flag in required)
            or any(flag in command for flag in incompatible)):
        raise ValueError("Expected the original all-visit two-scan anchor entry")
    command[5] = str(HERE / "combined_raw_research.py")
    command[command.index("--output") + 1] = str(output)
    command.append(FLAG)
    return command


def work(case, root):
    from full_short_physical import CACHE_LIB, CACHE_SHA
    from joint_held_north_raw import cache_snapshot_for_run
    from leo.storage.fast_scan import FastScanStore
    from north_held_anchor_pair import tmpfs
    from raw_cfo_north_trial import workload
    from south_cfo_route import assigned, residency
    from tools.pipeline_eval.qualification.cache_residency import load_query

    if case == "north":
        request, manifests = workload(root)
        checked(CACHE_LIB, CACHE_SHA)
        query, store = load_query(CACHE_LIB), FastScanStore(root)

        def snapshot():
            return cache_snapshot_for_run(store, request, manifests, query)
    else:
        request, chunks = assigned()

        def snapshot():
            from south_cfo_route import admissible

            observed = residency(chunks)
            if not admissible(observed):
                raise ValueError(f"The original South input is incompletely resident: {observed}")
            return observed

    for path in (root.parent, request["recording"], request["archive"]["root"], request["saved_inventory"]):
        tmpfs(path)
    return request, snapshot


def prepare(case, root):
    from combined_raw_trial import checked_producer
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for

    old_root, binding, _, _ = control(case)
    machine = host()
    if binding["machine"] != machine:
        raise ValueError("The original CPU, priority and numeric thread configuration changed")
    for entry in binding["libraries"].values():
        checked(Path(entry["path"]), entry["sha256"])
    for name, pin in ADAPTER.items():
        checked(HERE / name, pin)
    git = ["git", "-C", str(CHECKOUT)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("Commit the source and protocol before staging the request")
    commit = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    root.parent.resolve(strict=True)
    request, snapshot = work(case, root)
    if request != binding["request"]:
        raise ValueError("The enrolled signed case or offered square changed")
    producer = checked_producer(request["cutoff_utc_ns"])
    command = adaptive_command(binding["command"], root / "containing")
    root.mkdir()
    (root / "tmp").mkdir()
    shutil.copytree(old_root / "fonts", root / "fonts")
    env = environment_for(root)
    help_text = subprocess.run([*command[:7], "--help"], capture_output=True, env=env, check=True, timeout=10).stdout
    if not all(flag.encode() in help_text for flag in (FLAG, "--held-anchor-route", "--named-survivor-finish")):
        raise ValueError("The normal raw entry failed the isolated parser preflight")
    names = (Path(__file__).name, "adaptive-raw-protocol.md", "combined_raw_research.py",
             "unified_short_bootstrap.py", *ADAPTER)
    enrollment = dict(case=case, original=binding["command"], command=command, clip=request, machine=machine,
                      libraries=binding["libraries"], producer=producer, commit=commit, control_pins=CONTROLS[case][1],
                      sources={name: sha256((HERE / name).read_bytes()).hexdigest() for name in names},
                      south_wall_gate_s=SOUTH_WALL_GATE_S)
    write(root / "binding.json", enrollment)
    write(root / "prepared-cache.json", snapshot())


def launch(root, *, north=None):
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for
    from short_raw_diagnostic import measure

    enrollment = read(root / "binding.json")
    case = enrollment["case"]
    if case == "south" and (north is None or not read(north / "result.json")["admit_south"]):
        raise ValueError("South requires the qualified North result")
    _, binding, _, _ = control(case)
    out = root / "containing"
    if (out.exists() or (root / "clock.json").exists() or enrollment["machine"] != host()
            or enrollment["command"] != adaptive_command(binding["command"], out)):
        raise ValueError("The frozen request is already spent or no longer applies")
    for name, pin in enrollment["sources"].items():
        checked(HERE / name, pin)
    request, snapshot = work(case, root)
    if request != enrollment["clip"]:
        raise ValueError("The signed workload changed since preparation")
    write(root / "cache-before.json", snapshot())
    clock = measure(enrollment["command"], environment_for(root), out)
    write(root / "clock.json", clock)
    write(root / "cache-after.json", snapshot())
    return clock


def missed_low_points(grid, full, *, threshold=4.5):
    from leo.contracts.position_grid import ARMS

    active = {(row["east_km"], row["north_km"]) for row in grid["points"]}
    result = {}
    for arm in ARMS:
        minimum = min(row["scores"][arm] for row in full["points"] if row["scores"][arm] is not None)
        result[arm] = []
        for row in full["points"]:
            offset, value = (row["east_km"], row["north_km"]), row["scores"][arm]
            if offset not in active and value is not None and value <= minimum + threshold:
                result[arm].append(dict(east_km=offset[0], north_km=offset[1], latlon=row["latlon"],
                                        score=value, excess_loss=value-minimum))
    return result


def same_page_counts(before, after):
    fields = ("members", "observed_members", "observed_file_pages", "cached_pages", "unavailable")
    return before.keys() == after.keys() and all(
        all(before[name][field] == after[name][field] for field in fields) for name in before)


def score(root):
    from eight_ms_south_transfer import verify_options
    from joint_publication import figure_evidence
    from leo.contracts.digests import canonical_digest, sha256_digest
    from leo.contracts.fast_standard_analysis import PLOTS
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from raw_cfo_north_trial import native_file
    from reports.ALGO08.v3.live_adaptive_grid import quality
    from reports.ALGO08.v3.live_adaptive_grid_entry import NAMESPACE, read_manifest, read_sidecar, research_folder

    enrollment, clock = (read(root / f"{name}.json") for name in ("binding", "clock"))
    case = enrollment["case"]
    prior, _, old, old_research = control(case)
    candidate, reference = root / "containing", prior / "containing"
    raw = read(candidate / "unified-short-bootstrap.json") if clock["exit_code"] == 0 else None
    result = dict(case=case, clock=clock, ordinary_clock=old["clock"], receipt=raw and raw["receipt"],
                  passed=False, admit_south=False, binding_sha256=sha256((root/"binding.json").read_bytes()).hexdigest())
    if raw is None or raw["receipt"]["decision"] != "complete":
        write(root / "result.json", result)
        return result
    new = read(candidate / "joint-research-receipt.json")
    run = raw["receipt"]["run_id"]
    terminal = read(candidate / "fast-scan-automatic-work" / run / "terminal.json")
    store = FastStandardAnalysisStore(reference)
    full, old_path = store.position_grid(run), store.position_path(run)
    manifest = read_manifest(candidate, run)
    sample, path = (read_sidecar(candidate, run, name) for name in ("sample", "path"))
    old_plot = old_research["evidence"]["images"]
    folder = research_folder(candidate, run)
    images, reference_detail = {}, store.detail(run)
    for entry in manifest["publication"]["artifacts"]:
        name = entry["name"]
        data = (folder / (entry["sha256"][7:] + ".png")).read_bytes()
        observed = figure_evidence(data, sha256_digest(data))
        images[name] = dict(**observed, verified=(observed["sha256"] == entry["sha256"] and
                                                len(data) == entry["byte_count"] and
                                                observed["size"] == tuple(old_plot[name]["size"])),
                            same=observed["sha256"] == old_plot[name]["sha256"] and
                            observed["rgba_sha256"] == old_plot[name]["rgba_sha256"])
    for record in (path, old_path):
        record["binding"].pop("position_png_sha256")
    expected_calls = 2 * sample["evaluated_points"] - 2
    posterior = new["receipt"]["posterior_grid_handoff"]
    audit = quality(sample, full)
    delta = old["clock"]["elapsed_s"] - clock["elapsed_s"]
    cache_pre, cache_post = (read(root / f"cache-{phase}.json") for phase in ("before", "after"))
    raw_match = all(raw[name] == old["raw"][name] for name in RAW_IDENTITY)
    packet_path = native_file(candidate)
    checked(packet_path, old["raw"]["native_sha256"][7:])
    options = verify_options(root, 11, raw["receipt"]["decision"])
    png_reads = raw["verified_png_reads"]
    tests = dict(
        resident=same_page_counts(cache_pre, cache_post) and not clock["major_faults"] and not clock["input_blocks"],
        signed=raw_match and raw["raw_acquisitions"] == raw["verified_handoffs"] == 1 and not raw["scientific_imports_before"],
        terminal=canonical_digest(terminal) == old["raw"]["receipt"]["terminal_sha256"] and all(
            raw["receipt"][name] == old["raw"]["receipt"][name] for name in SCIENCE),
        fit=manifest["publication"]["arms"] == reference_detail["arms"] and
        new["selected_rows"] == old_research["selected_rows"] and
        new["solve"]["objective_replay"] == old_research["solve"]["objective_replay"] and
        raw["named_survivor_finish"] == old["raw"]["named_survivor_finish"],
        location=path == old_path and all(sample[name] == full[name] for name in
                                          ("endpoints", "endpoint_latlon", "region_center")),
        grid=audit["passed"] and posterior["factor_calls"] == posterior["prediction_calls"] == expected_calls,
        images=set(images) == set(PLOTS) and all(row["verified"] and (name == "position" or row["same"])
                                                for name, row in images.items()) and
        png_reads["reused"] == png_reads["verified"] == 8 and png_reads["fallbacks"] == 0,
        layout=raw["research_adaptive_position_map"] == dict(namespace=NAMESPACE, published=True) and
        not (candidate/"fast-scan-standard-v2").exists(),
    )
    result.update(passed=all(tests.values()), checks=tests, ordinary_elapsed_saved_s=delta,
                  admit_south=case == "north" and all(tests.values()) and delta >= SOUTH_WALL_GATE_S,
                  geographic=new["route_details"]["decision"], route=raw["held_anchor_route"]["choice"],
                  arms=manifest["publication"]["arms"], owners_sha256=canonical_digest(new["selected_rows"]),
                  owner_counts={arm: len(rows) for arm, rows in new["selected_rows"].items()}, phases=raw["phases"],
                  native_sha256=raw["native_sha256"], receiver_recipe_sha256=raw["detector_recipe_sha256"],
                  native_calls=raw["receiver_audit"]["native"]["native_calls"], evidence_clocks=new["route_details"]["standard_evidence_clocks"],
                  solve=new["solve"], options=options, images=images, layout=dict(
                      sampled=sample["evaluated_points"], full=full["evaluated_points"], audit=audit,
                      lost_low_points=missed_low_points(sample, full), actual_calls=sample["objective_calls"],
                      elapsed_s=sample["elapsed_seconds"], cpu_s=sample["sample_cpu_s"],
                      full_elapsed_s=full["elapsed_seconds"], phase_sha256=sample["phase_state_sha256"],
                      posterior_calls=expected_calls))
    write(root / "result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "launch", "score"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--case", choices=CONTROLS, default="north")
    parser.add_argument("--qualified-north", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.case, args.output)
    elif args.action == "launch":
        launch(args.output, north=args.qualified_north)
    else:
        score(args.output)
