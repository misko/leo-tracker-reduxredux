"""Reconstruct, price and stop after one archived causal finalist."""

import argparse
from contextlib import ExitStack, contextmanager
from hashlib import sha256
import json
from math import dist
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = Path("/dev/shm/leo-v3-causal-mask-dense-01")
STAGED = Path("/dev/shm/leo-held-anchor-selected-dense-01")
PINS = {
    ROOT / "request.json": "191d2b39af53069ed2db3eec9da2126dfddff3ee99d5b03a0caaf876c1839aeb",
    ROOT / "candidate-detections.json": "5a81919e3105ba2f38acfd401da91f828a9846f14b54de20d5e26165053e2c7b",
    ROOT / "dense/joint-research-receipt.json": "8dded884cd12d52f95d135d4da850fbb5f7dc62ee1252d7553a7065170668f61",
    HERE / "target_owner_recovery_trial.py": "9da442b4a2f917f27dbc134f59ca997f30efc65fa569fae76cc538c209dfd6e6",
    HERE / "prospective_0316_solver.py": "73e3fb562115933bd5f6fb28d7a3e281c11c8f11c834a45d4b1c0914c33a280c",
    HERE / "joint_publication.py": "9df6978f279577f972460a6b752511df9bf4c511e74d072ce4ff23ebd39ac5f7",
    HERE / "cold_finalist_race.py": "eeb7d1041f34fb7dbb805cb12eb93f66eba87e729e9cf695ff77811b51842fe7",
}


class CompleteScope(Exception):
    """Catch outside the saved worker, before it can continue to a terminal."""


def forbidden(*_args, **_options):
    raise RuntimeError("Installed solve fallback is forbidden in the isolated finalist scope")


def admission():
    from empty_bootstrap import checked

    for path, digest in PINS.items():
        checked(path, digest)
    request = json.loads((ROOT / "request.json").read_bytes())
    inventory = STAGED / "selected/fast-scan-inputs" / (request["session"] + ".json")
    checked(inventory, request["inventory"].removeprefix("sha256:"))
    reference = json.loads((ROOT / "dense/joint-research-receipt.json").read_bytes())
    if (reference["saved_digest"] != request["native_pin"] or reference["route"] != "complete"
            or reference["receipt"]["decision"] != "complete"):
        raise ValueError("The matched causal saved solution changed")
    for path in (Path(request["offer"]), Path(request["saved_file"]), Path(request["archive"]["root"]),
                 *(Path(name) for name in request["local_libraries"].values())):
        if not (path.resolve(strict=True).is_relative_to(STAGED) or path.resolve(strict=True).is_relative_to(ROOT)):
            raise ValueError("Only the already staged tmpfs inputs are eligible")
    return request, inventory, reference["route_details"]["cold"]


@contextmanager
def installed_optimizer(position, original, cell, mode, traces):
    from finalist_tangent import measured_optimizer

    operation = measured_optimizer(original, mode, traces)
    if cell is None:
        with patch.object(position, "bounded_gauss_newton", operation):
            yield
        return
    prior = cell.cell_contents
    cell.cell_contents = operation
    try:
        yield
    finally:
        cell.cell_contents = prior


def experiment(prepared, region, bound, archived):
    from blind_joint_finish import digest
    from cold_finalist_race import secant_port
    from leo.analysis.localization_v3 import position
    from leo.analysis.localization_v3.discovery import signature
    from tools.pipeline_eval.variants import v5_core

    start = process_time_ns(), perf_counter_ns()
    scan = v5_core.scan_context(prepared, region, digest(prepared["noise"]), bound, "previous")
    nodes = v5_core.ranked_initial_nodes(scan)
    if len(nodes) < 3 or len(scan.norads) != archived["catalogue"]:
        raise ValueError("The exact causal rank no longer yields the archived finalist roster")
    ranked = dict(cpu_ns=process_time_ns()-start[0], elapsed_ns=perf_counter_ns()-start[1],
                  ordered=[signature(node) for node in nodes])
    expected = max(archived["completed"], key=lambda item: item["first_evaluations"])
    node = nodes[expected["branch"]-1]
    active, cell = secant_port(position.bounded_gauss_newton)
    results = {}
    for mode in ("control", "tangent"):
        traces = []
        start = process_time_ns(), perf_counter_ns()
        with installed_optimizer(position, active, cell, mode, traces):
            model, fit, history = position.refreshed(scan, scan.radio_sigma_hz, node, "c0", rounds=2, iterations=48)
        results[mode] = dict(optimizer=traces, recorded=fit, phase_history=history, labels=model.labels,
                             active_rows=int(model.keep.sum()), phase_cpu_ns=process_time_ns()-start[0],
                             phase_elapsed_ns=perf_counter_ns()-start[1])
        if len(traces) != 2:
            raise ValueError("Exactly two ordinary cold phase refreshes are required")
        if mode == "control":
            first, second = (trace["result"] for trace in traces)
            if (first["evaluations"] != expected["first_evaluations"] or second["evaluations"] != expected["second_evaluations"]
                    or abs(first["score"] - expected["first_score"]) > 1e-8 or abs(second["score"] - expected["score"]) > 1e-8
                    or dist(expected["point"], second["parameters"]) > 1e-9 or second["stopped"] != expected["stopped"]):
                raise ValueError(f"The scoped control did not reconstruct the difficult finalist: {first['evaluations']}, "
                                 f"{second['evaluations']}, {first['score']}, {second['score']}, {second['parameters']}")
    first, next_ = (row["recorded"] for row in results.values())
    substituted = [dict(item, score=next_["score"]) if item["branch"] == expected["branch"] else item
                   for item in archived["completed"]]
    winner = min(substituted, key=lambda item: (item["score"], item["branch"]))["branch"]
    return dict(ranked=ranked, results=results, archived_finalist=expected,
                score_delta=next_["score"]-first["score"], endpoint_delta_km=dist(first["parameters"], next_["parameters"]),
                archived_winner=archived["branch"], winner_after_substitution=winner,
                curvature_scope="only the selected fixed-zero finalist, two original phase refreshes")


def worker(output, archived, inventory):
    import empty_bootstrap
    from aperture_trial import write
    from target_owner_recovery_trial import worker as original_worker

    installed = empty_bootstrap.load_runtime
    scoped = {}
    with ExitStack() as stack:
        def load_runtime():
            result = installed()
            import cold_finalist_race
            import joint_publication as joint

            ordinary_route = joint.full_catalogue_route

            def route(_installed, *args, **options):
                return ordinary_route(forbidden, *args, **options)

            def stop(mode, prepared, region, bound):
                if mode != "race" or scoped:
                    raise RuntimeError("Unexpected repeat of the exact scoped cold rank")
                try:
                    scoped.update(experiment(prepared, region, bound, archived))
                except Exception as error:
                    raise RuntimeError("The isolated finalist experiment failed") from error
                raise CompleteScope

            stack.enter_context(patch.object(joint, "full_catalogue_route", route))
            stack.enter_context(patch.object(cold_finalist_race, "refine", stop))
            return result

        stack.enter_context(patch.object(empty_bootstrap, "load_runtime", load_runtime))
        try:
            original_worker(ROOT / "request.json", inventory, output)
        except CompleteScope:
            if (not scoped or any(output.glob("fast-scan-automatic-work/*/terminal.json"))
                    or any(output.glob("fast-scan-standard-*/*/manifest.json"))):
                raise RuntimeError("The isolated cold test unexpectedly produced a terminal")
            write(output / "scoped.json", scoped)
            return
    raise RuntimeError("The one original cold boundary was never reached")


def run(root):
    from aperture_trial import RELEASE, read, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    machine = host()
    headroom = next(int(row.split()[1]) for row in Path("/proc/meminfo").read_text().splitlines()
                    if row.startswith("MemAvailable:"))
    if (subprocess.check_output(["findmnt", "-T", str(root.parent), "-no", "FSTYPE"], text=True).strip() != "tmpfs"
            or headroom < 3*1024**2):
        raise ValueError("Expected fresh tmpfs and memory headroom")
    request, _, archived = admission()
    if archive_identity(Path(request["archive"]["root"]))["snapshots_sha256"] != request["archive"]["snapshots_sha256"]:
        raise ValueError("Original causal archive changed")
    root.mkdir(exist_ok=False)
    (root / "tmp").mkdir()
    sources = (Path(__file__), HERE / "finalist_tangent.py", HERE / "finalist-tangent-protocol.md")
    write(root / "binding.json", dict(sources={str(path): sha256(path.read_bytes()).hexdigest() for path in sources},
                                      pins={str(path): pin for path, pin in PINS.items()}, machine=machine,
                                      request=request, archived_cold=archived, headroom_kib=headroom))
    env = environment(STAGED)
    env["TMPDIR"] = str(root / "tmp")
    out = root / "diagonal"
    clock = measure([RELEASE / "venv/bin/python", "-IB", __file__, "worker", out], env, out)
    write(root / "clock.json", clock)
    if clock["exit_code"]:
        raise RuntimeError(f"Scoped actual finalist failed; see {out.with_suffix('.stderr')}")
    write(root / "result.json", dict(clock=clock, scope=read(out / "scoped.json"), waveform_calls=0, terminals=0,
                                     binding_sha256=sha256((root / "binding.json").read_bytes()).hexdigest()))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "worker"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.mode == "run":
        run(args.output)
    else:
        _, inventory, archived = admission()
        worker(args.output, archived, inventory)
