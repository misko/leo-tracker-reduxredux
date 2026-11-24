"""Run the frozen integrated original-file pipeline on the known South simulation."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from shutil import copytree
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ENTRY = HERE / "integrated_original_entry.py"
PRIOR = Path("/dev/shm/leo-v3-strict-cairo-south-result01")
CONTROL_PIN = "e0ac0972934671d6536daed5ba64de4cf21f2d695bc51893c0720a08a7fef903"
PHYSICAL_PIN = "35d027c8a515882b87e15de2a3921506fa2f0543ae4d206cb7d883557b0ac77b"
MODES = ("containing", "near-omitted")


def invocation(old, request, mode, output):
    expected = {"--sparse8-primary", "--verify-original-once", "--history-risk-route", "--cairo-six-sheets"}
    if (Path(old[5]).name != ENTRY.name or not expected <= set(old)
            or any(arg.startswith(("--legacy-first-map-plan", "--legacy-map-custody", "--strict-packed")) for arg in old)):
        raise ValueError("Expected the original integrated verified-once invocation")
    argv = list(old)
    argv[5] = str(ENTRY)
    replacements = {"--recording": request["recording"], "--archive": request["archive"]["root"],
                    "--archive-sha256": request["archive"]["snapshots_sha256"], "--region": request["offers"][mode],
                    "--output": str(output)}
    for flag, value in replacements.items():
        if argv.count(flag) != 1:
            raise ValueError(f"Expected one {flag}")
        argv[argv.index(flag) + 1] = value
    return argv


def resident(request, chunks):
    from south_cfo_route import admissible, residency
    from south_strict_transfer import causal_cache

    recorded = residency(chunks)
    if not admissible(recorded):
        raise ValueError("The complete signed South originals and indexes are not resident")
    return dict(wave=recorded, causal=causal_cache(request))


def observe(path):
    from aperture_trial import write
    from empty_bootstrap import clock, now
    from south_cfo_route import assigned

    start = now()
    request, chunks = assigned()
    residence = resident(request, chunks)
    write(path, dict(inventory=request["inventory"], recording=request["recording"],
                     residence=residence, clock=clock(start), owner=os.geteuid()))


def launch(root, mode, controls, preflight):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for
    from empty_bootstrap import checked, clock, now
    from exact_named_raw import portable_binding, staged_path
    from integrated_original_entry import PNG_LIBRARY, PNG_SHA
    from short_raw_diagnostic import measure
    from south_cfo_route import admissible, assigned

    start = now()
    staged_path(root.parent)
    if not root.name.endswith("-" + mode):
        raise ValueError("Name the fresh output for its predeclared offer")
    if mode == "near-omitted":
        containing = root.with_name(root.name.removesuffix("-near-omitted") + "-containing")
        prior = json.loads((containing / "result.json").read_bytes())
        if (not prior["qualified"] or prior["mode"] != "containing"
                or prior["seal_sha256"] != sha256((containing / "prediction-seal.json").read_bytes()).hexdigest()
                or json.loads((containing / "prediction-seal.json").read_bytes()) != output_seal(containing)):
            raise ValueError("Near-omitted depends on a qualified sealed containing transfer")
    physical = json.loads(checked(staged_path(controls / "physical-admission.json", root=controls), PHYSICAL_PIN))
    request, chunks = assigned()
    prior = json.loads(checked(staged_path(controls / "south-result.json", root=controls), CONTROL_PIN))
    current = host()
    if not prior["qualified"] or request != prior["admission"]["request"] or current != physical["machine"]:
        raise ValueError("The signed South controls or Gauss boundary changed")
    for path in (request["recording"], request["archive"]["root"], request["saved_inventory"], *request["offers"].values()):
        staged_path(Path(path))
    for name, digest in physical["sources"].items():
        checked(ROOT / name, digest.removeprefix("sha256:"))
    for lib in physical["native"].values():
        checked(Path(lib["path"]), lib["sha256"].removeprefix("sha256:"))
    checked(PNG_LIBRARY, PNG_SHA)
    argv = invocation(physical["command"], request, mode, root / "candidate")
    from legacy_first_map_entry import parser
    args = parser().parse_args([value for value in argv[6:] if value != "--sparse8-primary"])
    portable = portable_binding(args, request["cutoff_utc_ns"])
    preflight_data = preflight.read_bytes()
    before = json.loads(preflight_data)
    owner = Path(request["recording"]).stat().st_uid
    if ((before["owner"], preflight.stat().st_uid) != (owner, owner)
            or (before["recording"], before["inventory"]) != (request["recording"], request["inventory"])
            or not admissible(before["residence"]["wave"])):
        raise ValueError("Expected passive residency witnessed by the original input owner")
    root.mkdir(mode=0o700)
    (root / "tmp").mkdir()
    copytree(staged_path(controls / "fonts", root=controls), root / "fonts")
    write(root / "admission.json", dict(mode=mode, command=argv, request=request, chunks=chunks, machine=current,
          baseline_sources=physical["sources"], physical_admission_sha256=PHYSICAL_PIN, controls_sha256=CONTROL_PIN,
          portable=portable, original_conditioning_bytes=0, prior_map_files_used=0, installed_children=0,
          candidate_children=1, owner_preflight_sha256=sha256(preflight_data).hexdigest(),
          git_revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
          protocol_sha256=sha256((HERE / "integrated-south-protocol.md").read_bytes()).hexdigest(), setup=clock(start)))
    env = environment_for(root)
    start, usage = now(), getrusage(RUSAGE_CHILDREN)
    probe = subprocess.run([*argv, "--first-map-setup-only"], env=env, capture_output=True, text=True, timeout=15)
    after = getrusage(RUSAGE_CHILDREN)
    write(root / "startup.json", dict(clock=clock(start), child_cpu_s=after.ru_utime + after.ru_stime
          - usage.ru_utime - usage.ru_stime, exit_code=probe.returncode, stdout=probe.stdout, stderr=probe.stderr))
    probe.check_returncode()
    scanner, solver = map(json.loads, probe.stdout.splitlines())
    if (not scanner["reached_scanner"] or scanner["waveform_opens"] or scanner["audit"]["authority_mode"] != "verified-once"
            or not solver["solver_setup"] or not solver["lookahead_setup"] or solver["waveform_opens"] or args.output.exists()):
        raise ValueError("The isolated startup did not bind the exact waveform-denied receiver and solver")
    measured = measure(argv, env, args.output)
    write(root / "candidate-clock.json", dict(clock=measured, cache_before=before, command=argv))
    write(root / "prediction-seal.json", output_seal(root))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest="action", required=True)
    passive = commands.add_parser("observe")
    passive.add_argument("path", type=Path)
    live = commands.add_parser("launch")
    live.add_argument("root", type=Path)
    live.add_argument("mode", choices=MODES)
    live.add_argument("controls", type=Path)
    live.add_argument("preflight", type=Path)
    args = cli.parse_args()
    if args.action == "observe":
        observe(args.path)
    else:
        launch(args.root, args.mode, args.controls, args.preflight)


if __name__ == "__main__":
    main()
