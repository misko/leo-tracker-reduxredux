"""Exercise one saved, dynamically triggered cumulative-to-named fallback."""

import argparse
from contextlib import ExitStack
from hashlib import sha256
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
RECOVERY_EXIT = 65


def first(output):
    from aperture_trial import write
    from cumulative_history_dispatch import NamedRecoveryRequired, at_installed_retry
    import empty_bootstrap as staged
    from named_history_once import HISTORY_SHA256, ORBIT_MODES_SHA256, POSITION_SHA256, checked, observe
    from named_history_once_trial import INVENTORY, REQUEST
    from prospective_0160_solver import FIX_PINS, SETTINGS
    from prospective_0316_solver import worker

    solve = []
    load_runtime = staged.load_runtime
    with ExitStack() as stack:
        def observed_runtime():
            result = load_runtime()
            from leo.analysis.localization_v3 import orbit_modes
            from tools import algo08_position, algo08_scan
            from tools.pipeline_eval.qualification import compact_history_replay

            orbit_source = staged.RELEASE / "src/leo/analysis/localization_v3/orbit_modes.py"
            checked(orbit_modes, orbit_source, ORBIT_MODES_SHA256)
            checked(algo08_position, staged.PAYLOAD / "tools/algo08_position.py", POSITION_SHA256)
            checked(compact_history_replay, staged.PAYLOAD / "tools/pipeline_eval/qualification/compact_history_replay.py",
                    HISTORY_SHA256)
            if (algo08_position.history_support is not compact_history_replay.history_support
                    or Path(orbit_modes.previous_bank.__code__.co_filename).resolve() != orbit_source):
                raise ValueError("Cumulative history decision does not use the released retry port")
            stack.enter_context(at_installed_retry(algo08_position, orbit_modes, compact_history_replay.subset))
            stack.enter_context(patch.object(algo08_scan, "solve", observe(algo08_scan.solve, solve)))
            return result

        stack.enter_context(patch.object(staged, "load_runtime", observed_runtime))
        try:
            worker(REQUEST, "cumulative", output, source_pins=FIX_PINS, inventory_file=INVENTORY, **SETTINGS)
        except NamedRecoveryRequired as required:
            if [stage["status"] for stage in solve] != ["raised"]:
                raise ValueError("The selector must see one failed ordinary solve") from required
            work = output / "fast-scan-automatic-work"
            if any(work.glob("*/terminal.json")) or any(output.glob("fast-scan-standard-*/*/manifest.json")):
                raise ValueError("A cumulative terminal was already published before the handoff") from required
            detection, = work.glob("*/detections.json")
            if sha256(detection.read_bytes()).hexdigest() != SETTINGS["native_sha"]:
                raise ValueError("Handed-off factors differ from the first attempt") from required
            write(output.with_name(output.name + "-history-handoff.json"), dict(
                required=required.event, solve=solve[0], native_sha256=SETTINGS["native_sha"],
                waveform_calls=0, trigger_boundary="installed cumulative history_support factory",
            ))
            return RECOVERY_EXIT
    return 0


def dispatch(output):
    from aperture_trial import read, write
    from prospective_0160_solver import NATIVE_SHA
    from short_raw_diagnostic import measure

    output.mkdir(exist_ok=False)
    first_output = output / "first"
    command = [sys.executable, "-IB", __file__, "first", first_output]
    initial = measure(command, os.environ.copy(), first_output)
    write(output / "first-clock.json", initial)
    marker = first_output.with_name(first_output.name + "-history-handoff.json")
    if initial["exit_code"] == 0 and not marker.exists():
        route = dict(selected="first", trigger=None, clocks={"first": initial})
    elif initial["exit_code"] == RECOVERY_EXIT and marker.is_file():
        handoff = read(marker)
        if handoff["native_sha256"] != NATIVE_SHA or handoff["waveform_calls"] or not handoff["required"]["failed_previous_norads"]:
            raise ValueError("The dispatched cumulative failure did not authenticate the known packet")
        named_output = output / "named"
        command = [sys.executable, "-IB", HERE / "named_history_once_trial.py", "worker", named_output]
        recovery = measure(command, os.environ.copy(), named_output)
        write(output / "named-clock.json", recovery)
        if recovery["exit_code"] != 0:
            raise RuntimeError(f"The named recovery worker failed; see {named_output.with_suffix('.stderr')}")
        route = dict(selected="named", trigger=handoff, clocks={"first": initial, "named": recovery})
    else:
        raise RuntimeError(f"Unrelated cumulative worker exit; see {first_output.with_suffix('.stderr')}")
    write(output / "selected-publication.json", route)
    print(route["selected"], flush=True)


def run(root):
    from aperture_trial import RELEASE, read, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from named_history_once_trial import CORRECTED, PINS, STAGED, evidence, validate
    from short_raw_diagnostic import measure

    machine = host()
    original = evidence()
    if subprocess.check_output(["findmnt", "-T", str(root.parent), "-no", "FSTYPE"], text=True).strip() != "tmpfs":
        raise ValueError("Cumulative diagnostic needs a new tmpfs root")
    root.mkdir()
    (root / "tmp").mkdir()
    output = root / "candidate"
    env = environment(STAGED)
    repo = HERE.parents[2]
    env["PYTHONPATH"] = f"{HERE}:{repo / 'src'}:{repo}"
    env["TMPDIR"] = str(root / "tmp")
    command = [RELEASE / "venv/bin/python", "-BPs", __file__, "dispatch", output]
    binding = root / "binding.json"
    sources = (Path(__file__), HERE / "cumulative_history_dispatch.py", HERE / "cumulative-history-dispatch-protocol.md",
               HERE / "named_history_once.py", HERE / "named_history_once_trial.py", HERE / "joint_publication.py",
               HERE / "prospective_0160_solver.py", HERE / "prospective_0316_solver.py")
    write(binding, dict(machine=machine, sources={path.name: sha256(path.read_bytes()).hexdigest() for path in sources},
                        inputs={str(path): pin for path, pin in PINS.items()}, command=list(map(str, command))))
    clock = measure(command, env, output)
    write(root / "clock.json", clock)
    if clock["exit_code"] != 0:
        raise RuntimeError(f"The isolated dispatch failed; see {output.with_suffix('.stderr')}")
    selected = read(output / "selected-publication.json")
    if selected["selected"] != "named" or selected["trigger"] is None:
        raise ValueError("The admitted history-support development input did not trigger named recovery")
    outcome = validate(output / "named", selected["clocks"]["named"], original)
    if not set(selected["trigger"]["required"]["failed_previous_norads"]) == {
        norad for event in outcome["stage_audit"]["events"] for norad in event["failed_previous_norads"]
    }:
        raise ValueError("Cumulative and named earlier-orbit failures differ")
    archived = original[STAGED / "stock-clock.json"]["timing"]
    write(root / "result.json", dict(case="DS30-0160", waveform_calls=0, matched_named_science=True, clock=clock,
                route=selected, outcome=outcome, archived_named_clock=archived,
                corrected_cumulative=original[CORRECTED / "joint-research-receipt.json"]["recovered_inference"],
                binding_sha256=sha256(binding.read_bytes()).hexdigest()))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("first", "dispatch", "run"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    sys.exit({"first": first, "dispatch": dispatch, "run": run}[args.mode](args.output))
