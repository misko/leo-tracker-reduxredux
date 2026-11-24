"""Pair installed and native 20/8 ms on the signed complete DS30-0107 stage."""

import argparse
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PROTOCOL = HERE / "eight-ms-0107-pair-protocol.md"
ORDER = ("candidate", "stock")
NORTH = ("eight-ms-native-live.json.gz", "2604afe118cebc24fa4fb0a975a439e5a6e9c2858ca4ae793dbc5b7f7afe7b9d")
GUARDED = ("combined-raw-0107.json.gz", "7c55ef7a275808653dadf544fb3a071865806e23dc6878b905b5c151f55a34f3")
SOURCES = (Path(__file__).name, PROTOCOL.name, "combined_raw_research.py", "unified_short_bootstrap.py",
           "eight_ms_native_receiver.py", "eight_ms_held_fit.py", "mixed_aperture_receiver.py", "short_graph_guard.py")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def archived(source):
    from empty_bootstrap import checked

    file, pin = source
    return json.loads(gzip.decompress(checked(HERE / "measurements" / file, pin)))


def candidate_command(previous, recording, archive, offer, target):
    args = list(previous)
    if (Path(args[5]).name != "combined_raw_research.py" or "--eight-ms-native-history" not in args
            or "--catalogue-block-rank" not in args or "--prove-no-active-curvature" not in args
            or any(flag in args for flag in ("--full-anchor-primary-library", "--anchored-cfo-pack",
                                            "--short-lane-mask", "--whole-stereo-blocks", "--select-before-cfo"))):
        raise ValueError("Require exactly the North native 8 ms receiver and original full anchors")
    args[5] = str(HERE / "combined_raw_research.py")
    for flag, value in (("--recording", recording), ("--archive", archive), ("--region", offer), ("--output", target)):
        args[args.index(flag) + 1] = str(value)
    return args


def verified_scope(staged, original):
    if (not os.path.ismount(original) or staged.stat().st_dev != Path("/dev/shm").stat().st_dev
            or os.stat(original)[:2] != os.stat(staged)[:2] or not os.statvfs(original).f_flag & os.ST_RDONLY):
        raise ValueError("Require the private read-only mount of the exact staged original")


def is_resident(scopes):
    return set(scopes) == {"payload", "index"} and all(
        item["members"] == item["observed_members"] == 1 and not item["unavailable"]
        and 0 < item["observed_file_pages"] == item["cached_pages"] for item in scopes.values())


def prediction_seal(root):
    paths = list(root.glob("*.json")) + list(root.glob("*.stdout")) + list(root.glob("*.stderr"))
    paths.extend(p for mode in ORDER for p in (root / mode).rglob("*") if p.is_file())
    return {str(p.relative_to(root)): digest(p) for p in sorted(paths) if p.name not in ("prediction-seal.json", "result.json")}


def launch(root, *, candidate_factory=candidate_command, extra_sources=()):
    from aperture_trial import write
    from combined_raw_trial import checked_producer
    from continued_cfo_small_raw import CASE, INPUTS, RECORDING, input_inventory, residency
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from full_short_physical import environment
    from full_short_run import EIGHT_MS_SHA
    from guarded_cfo_small_raw import PRIOR, PRIOR_RESULT, PRIOR_SEAL
    from short_raw_diagnostic import measure
    from tools.pipeline_eval.qualification.paired_publication import NAMED_V3, archive_identity, verified_v3

    verified_scope(PRIOR / RECORDING.name, RECORDING)
    previous = json.loads(checked(PRIOR / "result.json", PRIOR_RESULT))
    old = previous["admission"]
    checked(PRIOR / "prediction-seal.json", PRIOR_SEAL)
    offer, archive = PRIOR / "offer.json", PRIOR / "tle"
    checked(offer, old["offer_sha256"])
    if (root.parent.stat().st_dev != Path("/dev/shm").stat().st_dev or archive.stat().st_dev != root.parent.stat().st_dev
            or previous["prediction_seal_sha256"] != PRIOR_SEAL or archive_identity(archive)["snapshots_sha256"] != INPUTS.archive):
        raise ValueError("Historical authority and causal archive do not match the local stage")
    session, members = input_inventory()
    if (session != old["session"] or old["case"] != CASE.id or old["inventory"] != INPUTS.inventory
            or any(dict(path=str(p), bytes=n, sha256=sha) != old["members"][k] for k, (p, n, sha) in members.items())):
        raise ValueError("Canonical 29-window source or signed member identity changed")
    north = archived(NORTH)["raw_binding"]
    libraries = north["libraries"]
    if libraries["--short-binary"]["sha256"] != EIGHT_MS_SHA:
        raise ValueError("The short native ABI differs from North and South")
    for row in libraries.values():
        checked(Path(row["path"]), row["sha256"])
    checked_producer(INPUTS.cutoff_ns)
    named = verified_v3(NAMED_V3)
    if named != old["named"]:
        raise ValueError("The original named installed release differs")
    git = ["git", "-c", f"safe.directory={HERE.parents[2]}", "-C", str(HERE.parents[2])]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"]).strip():
        raise ValueError("Freeze the matched pair before launch")
    machine = host()
    root.mkdir()
    (root / "tmp").mkdir()
    args = {"candidate": candidate_factory(north["command"], RECORDING, archive, offer, root / "candidate"),
            "stock": [NAMED_V3, "--recording", RECORDING, "--region", offer, "--archive", archive, "--bulk-root", root / "stock"]}
    env = environment(root) | {"TMPDIR": str(root / "tmp"), "XDG_CACHE_HOME": str(root / "tmp")}
    write(root / "binding.json", dict(case=CASE.id, commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
          named=named, sources={name: digest(HERE / name) for name in (*SOURCES, *extra_sources)}, north_sha256=NORTH[1],
          order=ORDER, archive=INPUTS.archive, recording=str(RECORDING), stage=str(PRIOR / RECORDING.name),
          offer=old["offer"], offer_sha256=old["offer_sha256"], machine=machine, libraries=libraries, input=old["members"],
          historical_sha256=PRIOR_RESULT, expected_causal_cutoff_utc_ns=INPUTS.cutoff_ns,
          session=session, signed_raw_authority=old["raw_authority"], original_conditioning_bytes=0,
          commands={m: list(map(str, argv)) for m, argv in args.items()}))
    for mode in ORDER:
        target = root / mode
        if mode == "stock":
            target.mkdir()
        before = residency(members)
        if not is_resident(before):
            write(root / "stopped.json", dict(before=mode, residency=before, conditioning_bytes=0))
            break
        clock = measure(args[mode], env, target)
        after = residency(members)
        write(root / f"{mode}-clock.json", dict(clock=clock, command=list(map(str, args[mode])),
              cache_before=before["payload"] | {"index_cache": before["index"]},
              cache_after=after["payload"] | {"index_cache": after["index"]}))
        if not is_resident(after):
            write(root / "stopped.json", dict(after=mode, residency=after, conditioning_bytes=0))
            break
    write(root / "prediction-seal.json", prediction_seal(root))


def ordinary_withhold(run, candidate=False):
    receipt = run["science"]["receipt"]
    basic = (receipt["decision"] == "withheld" and run["science"]["reason"] == "no_active_curvature"
             and not run["figures"] and run["sidecars"] is None
             and all(row["latlon"] is None and row.get("rf_rms_hz") is None for row in run["science"]["arms"].values()))
    if not candidate:
        return basic
    bootstrap = run["bootstrap"]
    proof = bootstrap["graph_proof"]
    return (basic and run["factors"] > 0 and bootstrap["route"] == "authenticated_installed_graph_ineligible" and proof is not None
            and proof["proven"] and proof["native_sha256"] == run["native_sha256"])


def verify(root, output=None):
    from aperture_trial import read, write
    from combined_raw_trial import source_at
    from continued_cfo_small_raw import CASE, INPUTS
    from empty_bootstrap import checked
    from guarded_cfo_small_raw import PRIOR, PRIOR_RESULT
    from leo.contracts.digests import canonical_digest
    from raw_0016_best_score import process_rows
    from triage_bounds import calibration_comparison

    frozen = read(root / "prediction-seal.json")
    if frozen != prediction_seal(root):
        raise ValueError("Raw outputs changed before verification")
    binding = read(root / "binding.json")
    for name, pin in binding["sources"].items():
        if name == Path(__file__).name:
            source_at(binding["commit"], name, pin)
        else:
            checked(HERE / name, pin)
    clocks = {mode: read(root / f"{mode}-clock.json") for mode in ORDER if (root / f"{mode}-clock.json").exists()}
    def retained(row):
        return all(is_resident({"payload": row[f"cache_{at}"], "index": row[f"cache_{at}"]["index_cache"]})
                   for at in ("before", "after"))

    completed = [mode for mode, row in clocks.items() if row["clock"]["exit_code"] == 0 and retained(row)]
    old = json.loads(checked(PRIOR / "result.json", PRIOR_RESULT))
    north = archived(NORTH)
    combined = archived(GUARDED)
    recipe = north["scientific_seal"]["raw"]["receiver_recipe"]
    receiver_pin = canonical_digest(recipe)[7:]
    admission = dict(old["admission"], route_flags=[arg for arg in north["raw_binding"]["command"] if arg.startswith("--prove-")],
                     sources=binding["sources"])
    runs = process_rows(root, admission, INPUTS, modes=completed, candidate_recipe=receiver_pin, archive_root=PRIOR / "tle")
    expected = {mode: ordinary_withhold(run, candidate=mode == "candidate") for mode, run in runs.items()}
    if runs:
        calibrations = calibration_comparison({mode: run["science"] for mode, run in runs.items()}, CASE.id)
    else:
        calibrations = {}
    activation, acquisition = None, None
    if "candidate" in runs:
        raw = runs["candidate"]["bootstrap"]
        acquisition = raw["receiver_audit"]
        if (raw["receiver_recipe"] != recipe or acquisition["recording_authority"] != binding["signed_raw_authority"]
                or acquisition["issued"] != CASE.windows or sum(acquisition["native"]["native_calls"].values()) != 2*INPUTS.admitted
                or raw["held_anchor_route"]["refinement_calls"]):
            raise ValueError("Actual case changed the original North/South native receiver or raw authority")
        activation = {name: read(root / file) for name, file in (("orbit", "orbits-indexed.json"), ("rank", "catalogue-block-rank.json"))}
    write(output or root / "result.json", dict(case=CASE.id, launch_order=ORDER, clocks=clocks, expected_withholds=expected,
          modes=runs, calibrations=calibrations, activation=activation, receiver=acquisition,
          same_opportunities=len(runs) == 2 and runs["candidate"]["opportunities"] == runs["stock"]["opportunities"],
          historical=dict(prior_sha256=PRIOR_RESULT, combined_sha256=GUARDED[1],
              installed=old["runs"]["stock"]["process"]["clock"], selective12=old["runs"]["candidate"]["process"]["clock"],
              combined_guarded=combined["result"]["guarded"]["process"]["clock"]),
          prediction_seal_sha256=digest(root / "prediction-seal.json"), original_backing_bytes=0, conditioning_bytes=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("launch", "verify"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mode == "launch":
        if args.output is not None:
            parser.error("--output applies to the verified receipt")
        launch(args.root)
    else:
        verify(args.root, args.output)
