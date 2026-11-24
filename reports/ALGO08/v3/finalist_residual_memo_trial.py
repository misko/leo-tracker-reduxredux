"""Run one bounded saved phase with an exact same-closure residual memo."""

import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
from math import dist
from pathlib import Path
import resource
import subprocess
import sys
from time import perf_counter, process_time
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from finalist_rejection_bound import MEASUREMENTS, OPTIMIZER_PIN, TRACE, checked


RUNTIME = Path("/dev/shm/leo-v3-finalist-tangent/reports/ALGO08/v3")
DRIVER_PIN = "b84a2a0b84fec3101230200c97b476249d58beb57bcd5b96161f87cafb950e23"
CAPACITY = 8
CPU_BUDGET_S = 19.9


def times(start):
    return dict(cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1])


def original_trace():
    source = checked(MEASUREMENTS/"finalist-tangent-DS30-0008.json.gz", TRACE, zipped=True)
    return json.loads(source)["scope"]


def runtime():
    checked(RUNTIME/"finalist_tangent_trial.py", DRIVER_PIN)
    sys.path.insert(0, str(RUNTIME))
    import finalist_tangent_trial

    if Path(finalist_tangent_trial.__file__).resolve() != RUNTIME/"finalist_tangent_trial.py":
        raise ValueError("The saved phase must use the original archived preparation driver")
    return finalist_tangent_trial


@contextmanager
def use_optimizer(position, cell, operation):
    if cell is None:
        with patch.object(position, "bounded_gauss_newton", operation):
            yield
    else:
        original = cell.cell_contents
        cell.cell_contents = operation
        try:
            yield
        finally:
            cell.cell_contents = original


def experiment(prepared, region, bound, archived, *, started, expected):
    from blind_joint_finish import digest
    from cold_finalist_race import secant_port
    from finalist_residual_memo import ResidualMemo
    from leo.analysis.localization_v3 import position
    from leo.analysis.localization_v3.discovery import signature
    from tools.pipeline_eval.variants import v5_core

    rank_clock = process_time(), perf_counter()
    scan = v5_core.scan_context(prepared, region, digest(prepared["noise"]), bound, "previous")
    nodes = v5_core.ranked_initial_nodes(scan)
    ranked = json.loads(json.dumps([signature(node) for node in nodes]))
    if ranked != expected["ranked"]["ordered"] or len(scan.norads) != archived["catalogue"]:
        raise ValueError("Original exact association and cold seed order changed")
    chosen = max(archived["completed"], key=lambda item: item["first_evaluations"])
    if chosen != expected["archived_finalist"]:
        raise ValueError("Expected the historically enrolled hardest first phase")
    rank = times(rank_clock)
    control = expected["results"]["control"]["optimizer"][0]
    setup = times(started)
    projected = control["cpu_ns"]/1e9 - 0.561344080 + 0.10
    if setup["cpu_s"] + projected >= CPU_BUDGET_S:
        return dict(status="budget_before_optimizer", setup=setup, rank=rank, projected_phase_cpu_s=projected)
    original, cell = secant_port(position.bounded_gauss_newton)
    checked(Path(original.__code__.co_filename), OPTIMIZER_PIN)
    observed = {}

    def optimize(residual, *args, **kwargs):
        if observed or type(getattr(residual, "__self__", None)) is not position.NormalPosition:
            raise ValueError("Only one exact NormalPosition residual closure may enter this memo")
        begin = process_time(), perf_counter()
        memo = ResidualMemo(residual, capacity=CAPACITY)
        requests = []

        def tracked(point):
            if process_time()-started[0] >= CPU_BUDGET_S:
                raise RuntimeError("Saved finalist reached its hard numerical budget")
            r = memo(point)
            requests.append(dict(point=point.tolist(), score=float(r@r)))
            return r

        optimized = original(tracked, *args, **kwargs)
        observed.update(timing=times(begin), memo=memo.receipt(), requests=requests, result=optimized)
        return optimized

    begin = process_time(), perf_counter()
    with use_optimizer(position, cell, optimize):
        model, _, _ = position.refreshed(scan, scan.radio_sigma_hz, nodes[chosen["branch"]-1], "c0", rounds=1, iterations=48)
    fit_time = times(begin)
    got = json.loads(json.dumps(observed["result"], default=lambda value: value.tolist()))
    before = control["result"]
    archive_requests = [{key: row[key] for key in ("point", "score")} for row in control["full_calls"]]
    verification = dict(ordered_requests_exact=observed["requests"] == archive_requests, optimizer_exact=got == before,
                        accepted_history_exact=got["history"] == before["history"], endpoint_delta_km=dist(got["parameters"], before["parameters"]),
                        score_delta=got["score"]-before["score"], same_stop=got["stopped"] == before["stopped"],
                        recorded_rows_match=int(model.keep.sum()) == expected["results"]["control"]["active_rows"])
    return dict(status="complete", rank=rank, setup=setup, fit_scope=fit_time, optimizer=observed, verification=verification,
                prior_optimizer_cpu_s=control["cpu_ns"]/1e9,
                prior_two_phase_fit_elapsed_s=expected["results"]["control"]["phase_elapsed_ns"]/1e9,
                additional_waveform_reads=0, other_position_solves=0)


def worker(target):
    started = process_time(), perf_counter()
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    previous = runtime()
    _, inventory, archived = previous.admission()
    trace = original_trace()

    def one_phase(prepared, region, bound, bound_archive):
        return experiment(prepared, region, bound, bound_archive, started=started, expected=trace)

    with patch.object(previous, "experiment", one_phase):
        previous.worker(target, archived, inventory)


def run(root):
    from aperture_trial import RELEASE, read, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    machine = host()
    if subprocess.check_output(["findmnt", "-T", root.parent, "-no", "FSTYPE"], text=True).strip() != "tmpfs":
        raise ValueError("Use a fresh tmpfs stage for the one saved phase")
    previous = runtime()
    request, _, _ = previous.admission()
    if archive_identity(Path(request["archive"]["root"]))["snapshots_sha256"] != request["archive"]["snapshots_sha256"]:
        raise ValueError("Original staged causal archive changed")
    root.mkdir()
    (root/"tmp").mkdir()
    sources = (Path(__file__), HERE/"finalist-residual-memo-protocol.md", HERE/"finalist_residual_memo.py")
    binding = root/"binding.json"
    write(binding, dict(sources={str(path): sha256(path.read_bytes()).hexdigest() for path in sources},
                        archived_sources={str(path): pin for path, pin in previous.PINS.items()},
                        request=request, machine=machine, original_driver_sha256=DRIVER_PIN,
                        trace_sha256=TRACE, optimizer_sha256=OPTIMIZER_PIN))
    env = environment(previous.STAGED)
    env["TMPDIR"] = str(root/"tmp")
    output = root/"phase"
    command = [RELEASE/"venv/bin/python", "-IB", __file__, "worker", output]
    clock = measure(command, env, output)
    evidence = dict(clock=clock, command=list(map(str, command)), binding_sha256=sha256(binding.read_bytes()).hexdigest(), waveform_reads=0)
    write(root/"clock.json", evidence)
    if clock["exit_code"]:
        raise ValueError(clock["stderr_tail"])
    write(root/"result.json", dict(evidence, measured=read(output/"scoped.json")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "worker"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    {"run": run, "worker": worker}[args.mode](args.output)
