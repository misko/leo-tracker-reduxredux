"""Transfer the verified first-use map runtime to the original signed tiny fixture."""

import argparse
from pathlib import Path
import json
import shutil
import subprocess
import sys

from legacy_block_0107_metadata import checked, digest, direct_tmpfs, metadata


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
POSITIVE = Path("/dev/shm/leo-v3-legacy-first-use-0016-result02")
POSITIVE_PIN = "5d7355c5288124c039fd373c0aa0c0e555a029882fab0f75acef3c435f6a63e2"
ORDINARY = Path("/dev/shm/leo-v3-legacy-block-0107-result01")
ORDINARY_PIN = "f5c8b39c67f5ccc49f0ffa446d4144e62089ad7d8d20fe0459bc307b3d80ddae"
READY = Path("/dev/shm/leo-v3-legacy-all-0107-result01")
READY_PIN = "c86a21b1555be7d4cc6ef61e2f416dc9b89c40ab647e35eaaa55ea4c40289122"
CURRENT = Path("/dev/shm/leo-v3-lightweight-audit-0107-result01")
CURRENT_PIN = "64fa809fcff4f146244db5e2a5bcc354fbaca14d5da558d52e76df8096a74cd8"
LIBRARIES = ("history", "replay")
ENTRY = "reports/ALGO08/v3/legacy_first_map_entry.py"


def load(path):
    return json.loads(path.read_bytes())


def reference(root, pin):
    parsed = json.loads(checked(direct_tmpfs(root/"result.json"), pin))
    if not parsed["qualified"]:
        raise ValueError("First-use comparison needs the already verified physical result")
    return parsed


def command_for(positive, old, target, pin):
    args = list(positive)
    if Path(args[5]).name != Path(ENTRY).name or "--cairo-residual-layout" not in args or "--history-risk-route" not in args:
        raise ValueError("The exact first-use research entry is required")
    args[5] = str(ROOT/ENTRY)
    for field in ("--recording", "--archive", "--region", "--archive-sha256"):
        args[args.index(field)+1] = old[old.index(field)+1]
    for field, value in (("--output", target/"fused"), ("--legacy-first-map-plan", target/"expected-custody.json"),
                         ("--legacy-first-map-plan-sha256", pin)):
        args[args.index(field)+1] = str(value)
    return args


def launch(root):
    import empty_bootstrap as boot

    sys.path.extend((str(ROOT), str(boot.RELEASE/"src"), str(boot.RELEASE)))
    from aperture_trial import write
    from dense_geographic_trial import host
    from eight_ms_0107_pair import verified_scope
    from eight_ms_south_transfer import environment_for
    from exact_named_raw import staged_path
    from frame_portable_0016 import seal
    from raw_0016_best_trial import measure_mode
    from visit_frame_raw_0016 import resident

    began = boot.now()
    if root.exists() or direct_tmpfs(root.parent) != Path("/dev/shm"):
        raise ValueError("The original first-use transfer needs fresh private output")
    positive = reference(POSITIVE, POSITIVE_PIN)
    ordinary = reference(ORDINARY, ORDINARY_PIN)
    ready = reference(READY, READY_PIN)
    current = reference(CURRENT, CURRENT_PIN)
    machine = host()
    if machine != positive["admission"]["machine"] or machine != ordinary["admission"]["machine"]:
        raise ValueError("Use the same original low-priority core and environment")
    baseline = positive["admission"]["sources"]
    executed = {path: "sha256:"+digest(direct_tmpfs(ROOT/path).read_bytes()) for path in baseline}
    changed = [path for path in executed if baseline[path] != executed[path]]
    if changed != [ENTRY]:
        raise ValueError(f"Only the withhold-capable verified terminal guard may change: {changed}")
    observed = metadata(ROOT)
    req = observed["request"]
    rec = Path(req["recording"])
    if req != current["admission"]["request"] or req != ready["admission"]["request"]:
        raise ValueError("The signed tiny causal scope differs from the prepared controls")
    verified_scope(Path(observed["signed_stage"]), rec)
    physical = [staged_path(Path(row["path"]), root=rec) for row in observed["files"].values()]
    resident(physical)
    argv = positive["clock"]["command"]
    for name in LIBRARIES:
        flag = "--legacy-first-map-"+name
        path = direct_tmpfs(Path(argv[argv.index(flag)+1]))
        if path != POSITIVE/f"{name}.so":
            raise ValueError("The native decoder binary belongs to a different first-use run")
        checked(path, argv[argv.index(flag+"-sha256")+1])
    root.mkdir(mode=0o700)
    (root/"tmp").mkdir()
    shutil.copytree(POSITIVE/"fonts", root/"fonts")
    pin = ready["admission"]["plan_pin"]
    canonical = checked(direct_tmpfs(READY/"maps/custody.json"), pin)
    plan = json.loads(canonical)
    member, = plan["members"]
    if member["map_kind"] != "literal" or plan["raw_authority"] != req["authority"] or plan["windows"] != 29:
        raise ValueError("Only the independent literal-ready custody can predefine this build")
    (root/"expected-custody.json").write_bytes(canonical)
    command = command_for(argv, ordinary["admission"]["commands"]["ordinary"], root, pin)
    common = boot.clock(began)
    start = boot.now()
    probe = subprocess.run([*command, "--first-map-setup-only"], env=environment_for(root), capture_output=True,
                           text=True, timeout=12)
    write(root/"setup.json", dict(clock=boot.clock(start), exit_code=probe.returncode, stderr=probe.stderr, stdout=probe.stdout))
    if probe.returncode or not json.loads(probe.stdout)["reached_scanner"] or json.loads(probe.stdout)["waveform_opens"]:
        raise ValueError("The no-waveform setup probe did not reach the genuine first-use scanner")
    write(root/"admission.json", dict(request=req, metadata=observed, sources=executed, changed=changed, expected_plan=plan,
          first_use_reference=POSITIVE_PIN, ordinary_reference=ORDINARY_PIN, prepared_reference=CURRENT_PIN,
          map_ready_reference=READY_PIN, expected_custody=pin, abi=LIBRARIES, machine=machine, command=command,
          common_admission=common, old_map_bytes_read_before_child=0, original_payload_preparation_reads=0,
          original_replay_count=1, decoder_binaries_reused=True))
    try:
        measure_mode(root, "fused", command, environment_for(root), lambda: resident(physical))
    finally:
        write(root/"prediction-seal.json", seal(root))


def score(root):
    sys.path[:0] = [str(ROOT/"src"), str(ROOT)]
    from aperture_trial import write
    from frame_portable_0016 import seal
    from legacy_block_0107_score import snapshot

    log, book = (load(root/name) for name in ("fused-clock.json", "admission.json"))
    if (load(root/"prediction-seal.json") != seal(root) or log["command"] != book["command"]
            or any("sha256:"+digest((ROOT/rel).read_bytes()) != pin for rel, pin in book["sources"].items())):
        raise ValueError("The launched first-use comparison no longer matches its sealed publication")
    ordinary, current = reference(ORDINARY, ORDINARY_PIN), reference(CURRENT, CURRENT_PIN)
    candidate = root/"fused"
    observed = snapshot(candidate, log["clock"], book["request"])
    earlier = (ordinary["paired"]["ordinary"], current["proof"])
    if any(observed[key] != old[key] for old in earlier for key in ("native_digest", "terminal", "scan_digest", "graph_proof", "receiver_visits")):
        raise ValueError("Original science must equal both the ordinary and ready comparison")
    audit = load(candidate/"legacy-first-map-acquisition.json")
    row, = audit["members"]
    plan, = book["expected_plan"]["members"]
    bundle = candidate/"legacy-first-maps"
    if (any(row[key] != value for key, value in plan.items()) or audit["plan_sha256"] != book["expected_custody"]
            or audit["finished_raw_authority"] != book["request"]["authority"] or row["exceptional_ordinals"]
            or row["proof"]["prefix_bytes"] != 640_000 or row["proof"]["original_encoded_reused"] != plan["encoded"]
            or (bundle/"custody.json").read_bytes() != (root/"expected-custody.json").read_bytes()
            or checked(bundle/row["map"], row["map_sha256"]) != checked(READY/"maps"/row["map"], row["map_sha256"])):
        raise ValueError("The durable first-use literal map must verify byte for byte against the independent map")
    positive = reference(POSITIVE, POSITIVE_PIN)
    times = {}
    for metric in ("elapsed_s", "cpu_s"):
        value = log["clock"][metric]
        times[metric] = dict(fresh_first_use=value, ordinary=ordinary["clocks"]["ordinary"][metric],
            ready=current["fresh_process"][metric], prior_installed=ordinary["admission"]["installed_prior"][metric],
            positive_first_use=positive["clock"]["clock"][metric], admission=book["common_admission"][metric],
            with_admission=value+book["common_admission"][metric])
    write(root/"result.json", dict(qualified=True, case="DS30-0107", scientific=observed, clock=log["clock"],
          admission=book, measured_setup=load(root/"setup.json"), times=times, byte_exact_independent_map_and_custody=True,
          receiver_and_publication_both_matched=True, actual_map=audit, map_bytes=(bundle/row["map"]).stat().st_size,
          prediction_sha256=digest((root/"prediction-seal.json").read_bytes())))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("launch", "score"))
    cli.add_argument("root", type=Path)
    opts = cli.parse_args()
    {"launch": launch, "score": score}[opts.mode](opts.root)
