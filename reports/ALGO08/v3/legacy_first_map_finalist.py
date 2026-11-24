"""Measure the exact integrated no-plan option on its two resident physical controls."""

import argparse
import gzip
import json
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
import shutil
import subprocess
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:] = [str(HERE), *sys.path, str(ROOT)]

PREVIOUS = "edbaa35c4b18e9f593d1d7f7ac7928a1d6e65bc259d8e46a385c645fdb3f684d"
PORTS = (
    "legacy_first_map_finalist.py", "legacy-first-map-finalist-protocol.md",
    "legacy_first_map_acceleration.py", "legacy_first_map_panel.py", "causal_body_election.py",
    "grid_design_template.py", "grid_design_template.c", "grid_feature_projection.py", "grid_phase_state_reuse.py",
)
PAIRED = "tools/pipeline_eval/variants/experimental/paired_sha256"
PROJECTION = Path("/dev/shm/leo-grid-feature-projection-02/native-map.so")


def options(command, history, history_pin, spec, spec_pin):
    fresh = list(command)
    names = ("--legacy-first-map-history", "--legacy-first-map-history-sha256")
    if any(arg.startswith(("--legacy-first-map-plan", "--legacy-first-map-fast", "--legacy-map-custody")) for arg in fresh):
        raise ValueError("Use original first use with no waveform custody or prior acceleration")
    for name, value in zip(names, (history, history_pin), strict=True):
        fresh[fresh.index(name) + 1] = str(value)
    return fresh + ["--legacy-first-map-fast", str(spec), "--legacy-first-map-fast-sha256", spec_pin]


def compile_inputs(root):
    import empty_bootstrap as boot
    from grid_design_template import build
    from grid_feature_projection import LIBRARY_SHA
    from leo.contracts.digests import canonical_json_bytes
    from legacy_first_map_acceleration import SCHEMA
    from reports.ALGO08.v3 import legacy_fused_map as history
    from visit_frame_raw_0016 import digest

    began, before = boot.now(), getrusage(RUSAGE_CHILDREN)
    lib = root / "exact"
    lib.mkdir()
    hasher, template, decoder = (lib / leaf for leaf in ("paired.so", "template.so", "history.so"))
    command = ["cc", "-O3", "-std=c11", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror",
               "-Wno-deprecated-declarations", str(ROOT / (PAIRED + ".c")), "-o", str(hasher), "-lcrypto"]
    subprocess.run(command, check=True, timeout=15)
    build(template)
    history_build = history.build(decoder)
    boot.checked(PROJECTION, LIBRARY_SHA)
    prepared = dict(schema=SCHEMA, **{key: dict(path=str(path), sha256=digest(path))
                                   for key, path in (("hasher", hasher), ("template", template), ("projection", PROJECTION))})
    config = lib / "artifacts.json"
    config.write_bytes(canonical_json_bytes(prepared))
    after = getrusage(RUSAGE_CHILDREN)
    return dict(history=str(decoder), history_pin=history_build["binary_sha256"], history_build=history_build,
                spec=str(config), spec_pin=digest(config), artifacts=prepared, sha_build=command,
                clock=boot.clock(began), compiler_cpu_s=after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime)


def launch(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for
    import empty_bootstrap as boot
    from legacy_first_map_0016 import runtime_pins
    import legacy_first_map_panel as panel
    from raw_0016_best_trial import measure_mode
    from visit_frame_raw_0016 import resident

    began = boot.now()
    if root.parent.resolve() != Path("/dev/shm") or root.exists():
        raise ValueError("Use a new private tmpfs publication root")
    positive = panel.reference(panel.POSITIVE, panel.POSITIVE_PIN)
    tiny = panel.reference(panel.ORDINARY, panel.ORDINARY_PIN)
    machine = host()
    if machine != positive["admission"]["machine"] or machine != tiny["admission"]["machine"]:
        raise ValueError("The original low-priority single-core environment changed")
    inputs = {panel.ORDER[0]: panel.tiny_input(), panel.ORDER[1]: panel.positive_input(positive)}
    template = positive["clock"]["command"]
    replay = "--legacy-first-map-replay"
    boot.checked(Path(template[template.index(replay) + 1]), template[template.index(replay + "-sha256") + 1][7:])
    root.mkdir(mode=0o700)
    prepared = compile_inputs(root)
    sources = runtime_pins() | panel.source_pins([*(f"reports/ALGO08/v3/{name}" for name in PORTS),
                                                  PAIRED + ".py", PAIRED + ".c"])
    commands, admission = {}, {}
    for case in panel.ORDER:
        started = boot.now()
        folder = root / case
        folder.mkdir(mode=0o700)
        (folder / "tmp").mkdir()
        shutil.copytree(panel.POSITIVE / "fonts", folder / "fonts")
        scoped = tiny["admission"]["commands"]["ordinary"] if case == panel.ORDER[0] else template
        commands[case] = options(panel.command_for(template, scoped, folder / "fused"),
                                 prepared["history"], prepared["history_pin"], prepared["spec"], prepared["spec_pin"])
        admission[case] = boot.clock(started)
    revision = subprocess.check_output(
        ["git", "-c", f"safe.directory={ROOT}", "-C", ROOT, "rev-parse", "HEAD"], text=True).strip()
    write(root / "admission.json", dict(order=panel.ORDER, machine=machine, inputs=inputs, commands=commands,
          sources=sources, runtime_revision=revision, admission=admission, controller_admission=boot.clock(began),
          prior_map_files_used_by_candidate=0, original_waveform_bytes_opened_by_preflight=0,
          prepared=prepared, prior_first_use=PREVIOUS))
    for case in panel.ORDER:
        folder, argv = root / case, commands[case]
        usage, started = getrusage(RUSAGE_CHILDREN), boot.now()
        probe = subprocess.run([*argv, "--first-map-setup-only"], env=environment_for(folder),
                               capture_output=True, text=True, timeout=15)
        elapsed, after = boot.clock(started), getrusage(RUSAGE_CHILDREN)
        write(folder / "upfront-probe.json", dict(clock=elapsed, exit_code=probe.returncode, stdout=probe.stdout,
              stderr=probe.stderr, child_cpu_s=after.ru_utime+after.ru_stime-usage.ru_utime-usage.ru_stime))
        probe.check_returncode()
        diagnostic = json.loads(probe.stdout)
        if (diagnostic["waveform_opens"] or not diagnostic["reached_scanner"] or (folder / "fused").exists()
                or diagnostic["audit"]["authority_mode"] != "verified-first-use"
                or diagnostic["audit"]["acceleration"]["pin"] != prepared["spec_pin"]):
            raise ValueError("Expected the exact real first-use startup without waveform access")
    for case in panel.ORDER:
        folder = root / case
        measure_mode(folder, "fused", commands[case], environment_for(folder),
                     lambda: resident(inputs[case]["wavepaths"]), require_success=False)
    write(root / "prediction-seal.json", panel.panel_seal(root))


def score(root):
    from aperture_trial import write
    from empty_bootstrap import checked
    import legacy_first_map_panel as panel
    from visit_frame_raw_0016 import read

    prior = json.loads(gzip.decompress(checked(HERE / "measurements/legacy-first-use-original-panel.json.gz", PREVIOUS)))
    panel.score(root)
    receipt = read(root / "result.json")
    pin = receipt["admission"]["prepared"]["spec_pin"]
    evidence, ordinary, accelerated = {}, {}, {}
    for case, row in receipt["cases"].items():
        run = root / case / "fused"
        audit = read(run / "legacy-first-map-acquisition.json")
        if audit["acceleration"]["pin"] != pin:
            raise ValueError("Different acceleration artifacts ran")
        paths = dict(owned=sum(bool(member["owned_window_capacity"]) for member in audit["members"]),
                     prefix=sum(bool(member["hash_prefix"]) for member in audit["members"]))
        solver = audit["acceleration"]["solver"]
        if case == panel.ORDER[0]:
            if paths != dict(owned=0, prefix=1) or solver:
                raise ValueError("The partial/empty withholding must use the ring and skip solver hooks")
        elif (not paths["owned"] or paths["prefix"] != 13
                or not solver["election"]["counts"].get("initial_success")
                or not solver["grid"].get("projection", {}).get("grids")):
            raise ValueError("The supported fix did not exercise all measured optimizations")
        evidence[case] = dict(paths=paths, solver=solver, artifacts=audit["acceleration"]["artifacts"])
        ordinary[case] = prior["cases"][case]["clock"]["clock"]
        accelerated[case] = row["clock"]["clock"]
    from legacy_block_0107_score import speedup_gate

    gains = {key: speedup_gate({case: ordinary[case][key] for case in panel.ORDER},
                               {case: accelerated[case][key] for case in panel.ORDER}) for key in ("elapsed_s", "cpu_s")}
    write(root / "finalist.json", dict(**receipt, activation=evidence, earlier_first_use=ordinary,
          speed_vs_earlier_first_use=gains))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("launch", "score"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    {"launch": launch, "score": score}[args.mode](args.root)
