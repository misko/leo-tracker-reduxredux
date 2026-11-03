"""Profile fresh ALGO02 fitting from frozen public prepared inputs, without answers."""

import argparse
import json
import os
import shutil
import time
from pathlib import Path

from profile_algo07_glrt import PROFILE

# Deliberately excludes fit/progress/result files and every family-cavity result.
INPUTS = tuple("SCAN/" + name for name in (
    "bank.npz", "input_receipt.json", "nominal_elements.json", "observations.json",
    "prepared.json", "previous.tle", "previous_receipt.json", "radio_noise.json",
    "receipt.json", "selected.tle", "tracking.json", "tracks.json")) + (
    "causal_phase_history/SCAN.json", "causal_phase_history/SCAN_forecast.json",
    "causal_prior/SCAN/previous.tle", "causal_prior/SCAN/previous_receipt.json",
    "causal_prior/SCAN/receipt.json")


def read(path):
    return json.loads(path.read_text())


def copy_inputs(export, target):
    """Copy only prepared evidence, checking it against the public descriptor."""
    descriptor = read(export / "descriptor.json")
    if descriptor["terminal"]["state"] != "complete":
        raise ValueError("Completed public graph reference required")
    target.mkdir(parents=True, exist_ok=False)
    for name in INPUTS:
        source, destination = export / "inference" / name, target / name
        expected = descriptor["files"][name].removeprefix("sha256:")
        if source.is_symlink() or PROFILE.digest(source) != expected:
            raise ValueError("Prepared public input changed: " + name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if PROFILE.digest(destination) != expected:
            raise ValueError("Prepared input copy differs: " + name)
    return descriptor


def snapshot(args):
    export, runtime = args.export.resolve(strict=True), args.runtime.resolve(strict=True)
    if not PROFILE.verify(export / "frozen.json")["verified"]:
        raise ValueError("Frozen public export changed")
    output = PROFILE.destination(args.output)
    output.mkdir(parents=True, exist_ok=False)
    descriptor = copy_inputs(export, output / "input")
    release = runtime / "release-manifest.json"
    manifest = read(release)
    files = [dict(path=str(output / "input" / name)) for name in INPUTS]
    for name, expected in manifest["files_sha256"].items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe runtime member")
        files.append(dict(path=str(runtime / name), sha256=expected))
    files.append(dict(path=str(release)))
    provenance = dict(runtime=str(runtime), job_id=descriptor["job_id"],
        native_input_sha256=descriptor["input_sha256"],
        reference_terminal=descriptor["terminal_receipt"],
        source_export=str(export),
        source_export_manifest_sha256=PROFILE.digest(export / "frozen.json"),
        prepared_inputs=list(INPUTS), scientific_reference_used_as_input=False,
        scope="Prepared graph observations and causal catalogue through fresh ALGO02 fitting")
    PROFILE.write_new(output / "source.json", provenance)
    files.append(dict(path=str(output / "source.json")))
    PROFILE.write_new(output / "spec.json", dict(files=files))
    frozen = PROFILE.freeze(output / "spec.json", output / "frozen.json")
    print(json.dumps(dict(files=len(frozen["files"]), prepared_inputs=len(INPUTS))))


def audit(root, supervisor):
    receipts = [read(p) for p in (root / "read_receipts").glob("*.json")]
    observed = {r["pid"] for r in receipts}
    roots = sorted(r["pid"] for r in receipts if r["parent_pid"] == supervisor)
    expected = 2 + sum(len(r["python_spawns"]) for r in receipts)
    valid = (len(roots) == 2 and len(receipts) == len(observed) == expected
             and all(r["parent_pid"] in observed | {supervisor} for r in receipts)
             and not any(r["denied_paths"] for r in receipts))
    return dict(verified=valid, receipts=len(receipts), expected=expected,
                root_process_ids=roots, supervisor_pid=supervisor)


def run(args):
    if not 0 < args.timeout <= 1200:
        raise ValueError("Whole prepared replay budget must be in (0, 1200] seconds")
    began = time.monotonic()
    snapshot = args.snapshot.resolve(strict=True)
    if not PROFILE.verify(snapshot / "frozen.json")["verified"]:
        raise ValueError("Frozen input or runtime changed")
    source = read(snapshot / "source.json")
    members = {str(p.relative_to(snapshot / "input"))
               for p in (snapshot / "input").rglob("*") if p.is_file()}
    if source["prepared_inputs"] != list(INPUTS) or members != set(INPUTS):
        raise ValueError("Prepared input inventory differs from the evidence-only allowlist")
    runtime = Path(source["runtime"])
    output = PROFILE.destination(args.output)
    if not output.is_relative_to(snapshot) or output.is_relative_to(snapshot / "input"):
        raise ValueError("New trial directory within snapshot required")
    output.mkdir(parents=True, exist_ok=False)
    workspace = output / "inference"
    shutil.copytree(snapshot / "input", workspace)
    env = dict(PYTHONDONTWRITEBYTECODE="1", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1", PYTHONPATH=os.pathsep.join(str(runtime / p) for p in
            ("deploy/fast_graph_guard", "src", "tools")),
        LEO_FAST_GRAPH_RUN_ROOT=str(output),
        LEO_FAST_GRAPH_INPUT=str(workspace / "SCAN/tracking.json"),
        LEO_FAST_GRAPH_SOURCE_ROOT=str(runtime),
        LEO_FAST_GRAPH_TLE_ROOT=str(output / "unused-archive"),
        MPLCONFIGDIR=str(output / "matplotlib-cache"))
    previous = dict(os.environ)
    stages = []
    try:
        os.environ.update(env)
        for stage in ("algo02", "family"):
            remaining = args.timeout - (time.monotonic() - began)
            if remaining <= 0:
                raise TimeoutError("Whole prepared replay budget exhausted")
            script = runtime / "tools/algo02_scan.py"
            # Preserve production's discovery child followed by initial/ALGO02
            # fitting in the same parent process, including its cache lifetime.
            arguments = ["--run-dir", str(workspace), "--case", "SCAN", "--stage", "all"]
            if stage == "family":
                script = runtime / "tools/fast_graph_engine.py"
                arguments = ["--root", str(workspace), "--case", "SCAN"]
            result = PROFILE.run(argparse.Namespace(manifest=snapshot / "frozen.json",
                output=output / stage, script=script, stage="algo02-" + stage,
                timeout=remaining, arguments=arguments, no_cprofile=args.no_cprofile))
            stages.append(dict(name=stage, **result))
            if not result["successful_execution"]:
                break
    finally:
        os.environ.clear()
        os.environ.update(previous)
    receipt = audit(output, os.getpid())
    complete = len(stages) == 2 and all(s["successful_execution"] for s in stages)
    arms = None
    if complete:
        result = read(workspace / "family_cavity/position/SCAN.json")
        arms = result.get("policy_arms")
        complete = result.get("status") == "complete" and set(arms or {}) == {"c0", "fitted_c"}
    summary = dict(complete=complete and receipt["verified"], stages=stages,
        maximum_seconds=args.timeout,
        read_audit=receipt, seconds=time.monotonic() - began,
        endpoints={k: v["endpoint_latlon"] for k, v in (arms or {}).items()},
        accuracy_comparison_performed=False, native_GLRT_rerun=False,
        graph_construction_rerun=False, recovery_stages_ALGO03_to_07_rerun=False,
        production_modified=False)
    PROFILE.write_new(output / "result.json", summary)
    print(json.dumps(summary))
    if not summary["complete"]:
        raise SystemExit(1)


def compare_results(reference, candidate):
    """Exact scientific parity; validate hash links before normalizing accounting."""
    from compare_full_glrt_replays import differences

    names = ("SCAN/fit_radio_noise.json", "SCAN/progress_radio_noise.json",
             "SCAN/result.json", "SCAN/algo02_result.json",
             "family_cavity/SCAN_nominations.json", "family_cavity/position/SCAN.json")
    links = {("SCAN/algo02_result.json", "baseline_sha256"): "SCAN/result.json",
             ("family_cavity/position/SCAN.json", "nomination_sha256"):
             "family_cavity/SCAN_nominations.json"}
    data, hashes = [], []
    for root in (reference, candidate):
        produced = {str(p.relative_to(root)) for p in root.rglob("*.json")
                    if str(p.relative_to(root)) not in INPUTS}
        if produced != set(names):
            raise ValueError("Scientific result inventory differs from the compared files")
        rows = {name: read(root / name) for name in names}
        hashes.append({name: PROFILE.digest(root / name) for name in names})
        for name, arm_key in (("SCAN/result.json", "arms"),
                              ("SCAN/algo02_result.json", "policy_arms"),
                              ("family_cavity/position/SCAN.json", "policy_arms")):
            if set(rows[name][arm_key]) != {"c0", "fitted_c"}:
                raise ValueError("Missing calibration arm: " + name)
        for (name, key), target in links.items():
            if rows[name][key] != PROFILE.digest(root / target):
                raise ValueError("Changed scientific hash link: " + name + "/" + key)
            rows[name][key] = "<verified and independently compared>"
        # The public export retains its original local paths. Normalize them
        # only in these recorded provenance fields, without reading that path.
        discovery = rows["SCAN/fit_radio_noise.json"]
        prior = Path(discovery["physical_prior_previous_tle_path"])
        if prior.parts[-2:] != ("SCAN", "previous.tle"):
            raise ValueError("Unexpected prior provenance path")
        origin = prior.parent.parent
        discovered = []
        for path in discovery["input_read_paths"]:
            relative = str(Path(path).relative_to(origin))
            if relative not in INPUTS:
                raise ValueError("Discovery read outside prepared evidence: " + path)
            discovered.append(relative)
        discovery["input_read_paths"] = discovered
        discovery["physical_prior_previous_tle_path"] = "SCAN/previous.tle"
        for name, value in rows.items():
            if name != "SCAN/progress_radio_noise.json":
                seconds = value.pop("seconds")
                if not isinstance(seconds, (int, float)) or not 0 <= seconds < 1200:
                    raise ValueError("Invalid completed-stage accounting")
        data.append(rows)
    changed = list(differences(*data))
    return dict(exact=not changed, tolerance=0, files=len(names),
                difference_count=len(changed), first_differences=changed[:50],
                file_sha256=dict(reference=hashes[0], candidate=hashes[1]),
                both_calibration_arms_required=True,
                includes_satellites_owners_gates_objectives_and_optimizer_histories=True,
                ignored_accounting="Top-level seconds in five completed result files",
                normalized_provenance="Two checked result hash links and discovery input paths")


def compare(args):
    from compare_full_glrt_replays import argument

    snapshot, trial = args.snapshot.resolve(strict=True), args.trial.resolve(strict=True)
    if not trial.is_relative_to(snapshot) or trial == snapshot:
        raise ValueError("Trial must belong to this prepared snapshot")
    if not PROFILE.verify(snapshot / "frozen.json")["verified"]:
        raise ValueError("Frozen prepared input or runtime changed")
    source = read(snapshot / "source.json")
    export = Path(source["source_export"])
    if (PROFILE.digest(export / "frozen.json") != source["source_export_manifest_sha256"]
            or not PROFILE.verify(export / "frozen.json")["verified"]):
        raise ValueError("Original public reference export changed")
    result = read(trial / "result.json")
    checked = audit(trial, result["read_audit"]["supervisor_pid"])
    if not result["complete"] or checked != result["read_audit"] or not checked["verified"]:
        raise ValueError("Incomplete execution or read audit")
    for name in INPUTS:
        if PROFILE.digest(snapshot / "input" / name) != PROFILE.digest(trial / "inference" / name):
            raise ValueError("Prepared input changed during replay: " + name)
    for stage in ("algo02", "family"):
        launch, timing = (read(trial / stage / name) for name in ("launch.json", "timing.json"))
        script = Path(source["runtime"]) / "tools" / (
            "algo02_scan.py" if stage == "algo02" else "fast_graph_engine.py")
        command = launch["command"]
        if (launch["manifest_sha256"] != PROFILE.digest(snapshot / "frozen.json")
                or not timing["successful_execution"]
                or launch["script_sha256"] != PROFILE.digest(script)
                or str(script) not in command
                or argument(command, "--case") != "SCAN"
                or Path(argument(command, "--run-dir" if stage == "algo02" else "--root"))
                != trial / "inference"
                or (stage == "algo02" and argument(command, "--stage") != "all")):
            raise ValueError("Stage did not use the verified snapshot")
    comparison = compare_results(export / "inference", trial / "inference")
    comparison.update(read_audit=checked, frozen_inputs_verified=True,
                      compared_with="public historical terminal; not a paired new timing trial")
    PROFILE.write_new(PROFILE.destination(args.output), comparison)
    print(json.dumps({k: v for k, v in comparison.items() if k != "file_sha256"}))
    if not comparison["exact"]:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("snapshot")
    p.add_argument("--export", type=Path, required=True)
    p.add_argument("--runtime", type=Path, required=True)
    p = commands.add_parser("run")
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--timeout", type=float, default=1200)
    p.add_argument("--no-cprofile", action="store_true")
    p = commands.add_parser("compare")
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--trial", type=Path, required=True)
    for p in commands.choices.values():
        p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    {"snapshot": snapshot, "run": run, "compare": compare}[args.command](args)


if __name__ == "__main__":
    main()
