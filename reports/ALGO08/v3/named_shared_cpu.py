"""Attribute exclusive CPU across exact named solver stages on the pinned saved request."""

import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack, contextmanager
from cProfile import Profile
from functools import wraps
from pathlib import Path
from pstats import Stats
import struct
import sys
from time import process_time, process_time_ns
from unittest.mock import patch
from weakref import ref


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

import exact_named_route as route
from named_inference_budget import CONTROL, CONTROL_SHA, launch, wall_and_decisions


DRIVER = Path(__file__).resolve()
PROTOCOL = HERE/"named-shared-cpu-protocol.md"
KEY_BYTES = 8 * 1024**2
GEOMETRY = {"phase_shifted_states", "interpolate_states", "paired_phase_states", "interpolate_selection"}
SIGHTLINE = {"look_angles", "phase_frequency_from_states", "phase_frequency_grid", "paired_phase_frequency",
             "ecef_to_enu_matrix", "geodetic_to_ecef_km"}
ASSEMBLY_FILES = {"algo08_curved_design.py", "continuous_curve_fit.py", "predictive_linear.py", "marginal.py"}
ASSEMBLY_FUNCTIONS = {"selected_design", "_selected_design", "calculate", "geometry_features", "make_problem"}
CAST_NAMES = {"asarray", "ascontiguousarray", "astype", "copy", "array", "frombuffer", "packbits", "tobytes"}


def family(name):
    file, _, function = name
    module = Path(file).name
    if module == "orbit_projector.py" and function == "evaluate":
        return "native_stencil_projection"
    if function in GEOMETRY and module in {"orbit_phase_geometry.py", "track_catalogue_geometry.py",
                                           "prepared_phase_geometry.py", "continuous_curve_fit.py"}:
        return "orbit_interpolation"
    if function in SIGHTLINE and module in {"frames.py", "orbit_phase_geometry.py", "continuous_curve_fit.py"}:
        return "line_of_sight"
    if module in ASSEMBLY_FILES and function in ASSEMBLY_FUNCTIONS:
        return "model_assembly"
    if ((module == "native_bound.py" and function in {"__call__", "pointer"})
            or (module == "algo08_posterior_handoff.py" and function in {"run", "predictive_factor"})
            or (module == "hierarchical.py" and function == "hierarchical_bound")):
        return "likelihood_and_native_bridge"
    if "numpy" in function and any(f".{name}>" in function or f"'{name}'" in function for name in CAST_NAMES):
        return "array_cast_or_copy"
    if "numpy.ufunc" in function and "'reduce'" in function:
        return "numpy_reduction"
    if function == "<built-in method _hashlib.openssl_sha256>" or "'update' of '_hashlib.HASH'" in function:
        return "sha256_and_hash_updates"
    return "other"


def records(profiles):
    categories = defaultdict(dict)
    totals = {}
    leaves = defaultdict(dict)
    for stage, profile in profiles.items():
        counts = defaultdict(lambda: [0, 0.0])
        stats = Stats(profile)
        totals[stage] = dict(calls=stats.total_calls, exclusive_cpu_s=stats.total_tt)
        for name, (_, calls, exclusive, inclusive, callers) in stats.stats.items():
            label = family(name)
            counts[label][0] += calls
            counts[label][1] += exclusive
            if exclusive >= 0.001 or label != "other":
                direct = sorted(callers.items(), key=lambda item: -item[1][2])[:4]
                leaves[name][stage] = dict(calls=calls, exclusive_cpu_s=exclusive, inclusive_cpu_s=inclusive,
                                          callers=[[list(k), v[1], v[2]] for k, v in direct])
        for label, (calls, cpu) in counts.items():
            categories[label][stage] = dict(calls=calls, exclusive_cpu_s=cpu)
    ordered = sorted(leaves, key=lambda name: -sum(row["exclusive_cpu_s"] for row in leaves[name].values()))
    return dict(stages=totals, groups=dict(categories), leaves=[dict(source=list(name), group=family(name),
                stages=leaves[name]) for name in ordered[:180]])


class Repeats:
    """Count exact repeated arguments on surviving same-object immutable inputs."""

    def __init__(self, *, key_bytes=KEY_BYTES):
        self.owners = {}
        self.sequence = 0
        self.bytes_left = key_bytes
        self.first = {}
        self.counts = defaultdict(Counter)

    def token(self, owner):
        address = id(owner)
        saved = self.owners.get(address)
        if saved and saved[0]() is owner:
            return saved[1]
        self.sequence += 1
        self.owners[address] = (ref(owner), self.sequence)
        return self.sequence

    def record(self, operator, stage, arguments, ns):
        row = self.counts[operator, stage]
        row.update(calls=1, inclusive_cpu_ns=ns)
        if arguments is None:
            row.update(unknown=1, unknown_cpu_ns=ns)
            return
        key = operator, arguments
        earlier = self.first.get(key)
        if earlier is not None:
            row.update(repeats=1, repeat_cpu_ns=ns)
            if stage != earlier:
                row.update(cross_stage_repeats=1, cross_stage_repeat_cpu_ns=ns)
            return
        needed = sum(len(item) for item in arguments if isinstance(item, bytes)) + 256
        if needed > self.bytes_left:
            row.update(unknown=1, capacity_excluded=1, unknown_cpu_ns=ns)
            return
        self.bytes_left -= needed
        self.first[key] = stage
        row.update(first=1, first_cpu_ns=ns)

    def report(self):
        return [dict(operator=operator, stage=stage, **row) for (operator, stage), row in sorted(self.counts.items())]


@contextmanager
def measured_nodes(audit):
    import numpy as np
    from leo.analysis.localization_v3 import conservative_recovery, family_cavity, history_policy, orbit_modes, screen_geometry, signed_context
    from leo.analysis.research import orbit_phase_geometry, phase_linear_geometry
    from tools import algo08_position
    from tools.pipeline_eval.variants import orbit_projector, v5_core, v5_screen_winner

    profilers = defaultdict(lambda: Profile(timer=process_time))
    repeats = Repeats()
    active_stage = None

    def profiled(operation, label):
        @wraps(operation)
        def run(*args, **kwargs):
            nonlocal active_stage
            if active_stage is not None:
                raise ValueError(f"Expected disjoint stage scopes, got {active_stage} inside {label}")
            active_stage = label
            profile = profilers[label]
            try:
                return profile.runcall(operation, *args, **kwargs)
            finally:
                active_stage = None
        return run

    phase_shifted = orbit_phase_geometry.phase_shifted_states
    evaluate = orbit_projector.Projector.evaluate
    infer = v5_core.infer

    def shifted(bank, time_s, phase_seconds):
        key = None
        if type(bank) is orbit_phase_geometry.FrozenOrbitBank:
            time = np.asarray(time_s, dtype=np.float64)
            phase = np.asarray(phase_seconds, dtype=np.float64)
            key = (repeats.token(bank), time.shape, phase.shape, time.tobytes(), phase.tobytes())
        start = process_time_ns()
        result = phase_shifted(bank, time_s, phase_seconds)
        repeats.record("phase_shifted_states", active_stage or "between_ports", key, process_time_ns()-start)
        return result

    def projected(projector, grid, latitude_deg, longitude_deg, *, altitude_m=0.0, rf_hz=11.5e9):
        key = None
        if type(grid) is orbit_projector.Stencil and all(not a.flags.writeable for a in
                (grid.positions, grid.velocities, grid.index, grid.fraction, grid.rotation)):
            key = (repeats.token(projector), repeats.token(grid), struct.pack(">dddd", latitude_deg, longitude_deg, altitude_m, rf_hz))
        start = process_time_ns()
        result = evaluate(projector, grid, latitude_deg, longitude_deg, altitude_m=altitude_m, rf_hz=rf_hz)
        repeats.record("native_stencil", active_stage or "between_ports", key, process_time_ns()-start)
        return result

    def inference(prepared, region, bound, stage_s, **kwargs):
        with ExitStack() as stack:
            for owner, name, label in (
                (v5_core, "scan_context", "scan"),
                (v5_core, "ranked_initial_nodes", "rank"),
                (v5_screen_winner, "screen_nodes", "screen"),
                (conservative_recovery, "conservative_recovery", "conservative"),
                (history_policy, "history_policy", "history"),
                (signed_context, "signed_context", "signed"),
                (family_cavity, "nominate_families", "nomination"),
                (family_cavity, "cavity_policy", "cavity"),
                (algo08_position, "selected_packet", "evidence"),
            ):
                stack.enter_context(patch.object(owner, name, profiled(getattr(owner, name), label)))
            result = infer(prepared, region, bound, stage_s, **kwargs)
        audit["inference"].append(wall_and_decisions(result, stage_s))
        return result

    try:
        with ExitStack() as stack:
            for module in (orbit_phase_geometry, phase_linear_geometry, orbit_modes, screen_geometry):
                if getattr(module, "phase_shifted_states", None) is phase_shifted:
                    stack.enter_context(patch.object(module, "phase_shifted_states", shifted))
            stack.enter_context(patch.object(orbit_projector.Projector, "evaluate", projected))
            stack.enter_context(patch.object(v5_core, "infer", inference))
            prepare = profiled(algo08_position.prepare_native_scan, "prepare")
            stack.enter_context(patch.object(algo08_position, "prepare_native_scan", prepare))
            yield
    finally:
        audit["profiles"] = records(profilers)
        audit["repeat_inputs"] = repeats.report()
        audit["repeat_key_bytes"] = KEY_BYTES - repeats.bytes_left


def source_paths():
    from aperture_trial import RELEASE
    payload = Path("/opt/leo-algo08/algo08v3/payload")
    src = RELEASE/"src/leo"
    return tuple(path.resolve() for path in (
        HERE/"named_inference_budget.py",
        payload/"tools/pipeline_eval/variants/orbit_projector.py",
        payload/"tools/pipeline_eval/variants/orbit_projector.c",
        src/"analysis/research/orbit_phase_geometry.py",
        src/"analysis/research/track_catalogue_geometry.py",
        src/"analysis/localization_v4/native_bound.py",
        src/"sky/frames.py",
    ))


def worker(output):
    from aperture_trial import write

    binding = route.read(output/"study-binding.json")
    if (binding["driver_sha256"] != route.digest(DRIVER) or binding["protocol_sha256"] != route.digest(PROTOCOL)
            or binding["sources"] != {str(path): route.digest(path) for path in source_paths()}):
        raise ValueError("The profiled sources changed after enrollment")
    original = route.exact_ports
    audit = dict(inference=[])

    @contextmanager
    def ports(*args, **kwargs):
        with original(*args, **kwargs), measured_nodes(audit):
            yield

    try:
        with patch.object(route, "exact_ports", ports):
            route.worker("0316", output)
    finally:
        write(output/"shared-profile.json", audit)


def score(output):
    from aperture_trial import write
    from exact_named_route_score import verify

    verify("0316", output)
    actual = route.read(output/"result.json")
    old = route.read(CONTROL/"result.json")
    if (not actual["exact"] or route.digest(CONTROL/"result.json") != CONTROL_SHA
            or actual["ordered_owner_sha256"] != old["ordered_owner_sha256"] or actual["geography"] != old["geography"]):
        raise ValueError("Profiling did not preserve the original exact science")
    profile = route.read(output/"shared-profile.json")
    if len(profile["inference"]) != 1:
        raise ValueError("Expected precisely one completed inference")
    write(output/"shared-result.json", dict(parity=actual["parity"], profile=profile, clocks=actual["clocks"],
          solver=actual["artifacts"]["candidate"]["worker"]["solve"],
          observed_history=actual["ports"]["history"], geography=actual["geography"],
          ordered_owner_sha256=actual["ordered_owner_sha256"],
          bindings={name: route.digest(output/name) for name in
                    ("binding.json", "study-binding.json", "clock.json", "result.json", "shared-profile.json")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker", "score"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.action == "launch":
        launch(args.output, driver=DRIVER, protocol=PROTOCOL, extra_sources=source_paths())
    else:
        {"worker": worker, "score": score}[args.action](args.output)
