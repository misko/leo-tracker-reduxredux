"""Price exact shared arithmetic in current saved cold finalist fits."""

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
import ctypes as ct
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
from time import process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
BASE = "c9e65f02fc18e125d36a07f5eeef28823fc1343b"
PROFILER = "reports/ALGO08/single-core-2x/dense_likelihood_kernel_trial.py"
PROFILER_SHA = "5cc50db5be49af714a7405931849d89c64d4cf920994bcd6ecc77ca1e64dd276"
BINARY_SHA = "c649042b2a5ddf7890177d84b302a19edcf7a662aea16c18cb177317ccba818b"
ASSIGNMENTS = {
    "DS30-0402": ("leo-v3-saved-0402-pair-01",
                  "a2d730f64833eafd096877650e24b5c250b3bcfbef69d6bb5a44b70f0cbf1274",
                  "85d85bba133cadabd26bc41644ec9a1e39982c93d02325f9321772a73e0598b5"),
    "DS30-0374": ("leo-v3-0374-final-fit-result02",
                  "72ced1ad90e5d9b6783efd20d6de6cf19edcb054bf445633d00b2b0f99cc454f",
                  "657d0d8d300647c2e7a8d548ae0ff9bb355dad50fe249950c629d1e2ebd835c4"),
}


def load_profiler(output):
    git_root = HERE.parents[2]
    src = subprocess.check_output(["git", "-c", f"safe.directory={git_root}", "-C", str(git_root),
                                   "show", f"{BASE}:{PROFILER}"])
    if sha256(src).hexdigest() != PROFILER_SHA:
        raise ValueError("The validated stage profiler changed")
    namespace = {"__name__": "_released_bound_profiler"}
    exec(compile(src, str(HERE / "../single-core-2x/dense_likelihood_kernel_trial.py"), "exec"), namespace)
    locations = namespace["LOCATIONS"]
    index, = [i for i, (name, _) in enumerate(locations) if name == "mean_and_residual"]
    namespace["LOCATIONS"] = (*locations[:index], ("mean", locations[index][1]),
                              ("residual_energy", "        memset(energy,0,k*sizeof(double));"), *locations[index+1:])
    namespace["profile_build"](output)
    library = ct.CDLL(str(output))
    library.nb_read_profile.argtypes = [ct.POINTER(ct.c_uint64)]
    library.nb_read_profile.restype = None
    return library, ("setup", *(name for name, _ in namespace["LOCATIONS"]))


def output_bytes(arguments, shape):
    n, p, k = shape
    # Output blocks in original nb_run order, including prior precisions, iteration count and rates.
    widths = [8 * count for count in (p, n, k, p, arguments[11], 2)] + [ct.sizeof(ct.c_int), 8 * k]
    return tuple(ct.string_at(pointer, width) for pointer, width in zip(arguments[19:], widths, strict=True))


def observe_bound(original, library, phases, records, state):
    def bound(owner, raw, features, sigma, groups, *values, **options):
        if owner.manifest["binary_sha256"] != BINARY_SHA:
            raise ValueError("Expected the pinned native Gamma binary")
        run = owner.run
        instrumented = library.nb_run
        instrumented.argtypes = owner.library.nb_run.argtypes
        instrumented.restype = owner.library.nb_run.restype
        initial = process_time_ns()
        sample = dict(rows=len(raw), columns=features.shape[1], status="python_fallback", native_cpu_ns=0)
        shadow_cost = 0

        def shadow(*arguments):
            nonlocal shadow_cost
            start = process_time_ns()
            code = run(*arguments)
            checkpoint = process_time_ns()
            sample.update(status=code, native_cpu_ns=checkpoint-start)
            if code == 0:
                shape = len(raw), features.shape[1], len(set(groups.tolist()))
                expected = output_bytes(arguments, shape)
                observed = instrumented(*arguments)
                if observed != code or output_bytes(arguments, shape) != expected:
                    raise RuntimeError("The unchanged stock Gamma calculation and its observer disagree")
                counters = (ct.c_uint64 * len(phases))()
                library.nb_read_profile(counters)
                sample.update(phases=dict(zip(phases, list(counters), strict=True)),
                              iterations=ct.cast(arguments[25], ct.POINTER(ct.c_int)).contents.value)
            shadow_cost = process_time_ns()-checkpoint
            return code

        with patch.object(owner, "run", shadow):
            result = original(owner, raw, features, sigma, groups, *values, **options)
        sample.update(observed_bound_cpu_ns=process_time_ns()-initial, shadow_cpu_ns=shadow_cost)
        records.append(sample)
        state["shadow_cpu_ns"] += shadow_cost
        return result

    return bound


class Probes:
    def __init__(self):
        self.models = {}
        self.rows = []
        self.forward = None
        self.batches = []
        self.state = {"shadow_cpu_ns": 0}

    def points(self, original):
        def observe(anchor, lower, upper, step):
            locations = []
            for axis, nearby, delta in original(anchor, lower, upper, step):
                self.forward = axis, anchor.tobytes(), len(self.batches)
                try:
                    locations.append(nearby.tolist())
                    yield axis, nearby, delta
                finally:
                    self.forward = None
            self.batches.append(locations)
        return observe

    def calculations(self, original, native):
        def calculate(model, point, *values, **options):
            entry = self.models.setdefault(id(model), (len(self.models), model, set()))
            index, _, seen = entry
            key = point.tobytes()
            old_shadow, old_calls = self.state["shadow_cpu_ns"], len(native)
            start = process_time_ns()
            result = original(model, point, *values, **options)
            elapsed = process_time_ns()-start
            row = dict(model=index, exact_repeat=key in seen, location=point.tolist(),
                       stock_equivalent_cpu_ns=elapsed-(self.state["shadow_cpu_ns"]-old_shadow),
                       kernel_cpu_ns=sum(call["native_cpu_ns"] for call in native[old_calls:]))
            if self.forward is not None:
                axis, anchor, batch = self.forward
                row.update(axis=axis, anchor_previously_seen=anchor in seen, batch=batch)
            self.rows.append(row)
            seen.add(key)
            return result
        return calculate

    def counts(self):
        repeats = [row for row in self.rows if row["exact_repeat"]]
        derivatives = [row for row in self.rows if "axis" in row]
        return dict(calculations=len(self.rows), models=len(self.models), exact_repeats=len(repeats),
                    duplicate_cpu_ceiling_ns=sum(row["stock_equivalent_cpu_ns"] for row in repeats),
                    duplicate_kernel_ceiling_ns=sum(row["kernel_cpu_ns"] for row in repeats),
                    derivatives=len(derivatives),
                    derivatives_with_base=sum(row["anchor_previously_seen"] for row in derivatives),
                    derivative_exact_repeats=sum(row["exact_repeat"] for row in derivatives),
                    partner_shared_coordinates=dict(Counter(
                        sum(left == right for left, right in zip(*locations, strict=True))
                        for locations in self.batches if len(locations) == 2)))


class ColdComplete(BaseException):
    """The authenticated saved path reached the requested measurement cut."""


@contextmanager
def measure_cold(output, audit):
    import cold_finalist_race as race
    from leo.analysis.localization_v3.discovery import signature
    from leo.analysis.localization_v4.native_bound import NativeBound
    from tools.pipeline_eval.variants import compact_cavity_optimizer, v5_core

    original = race.refine
    partial = race.partial_fits
    library, phases = load_profiler(output)
    records, probes = [], Probes()

    def finalists(*args, **kwargs):
        from leo.analysis.localization_v3 import position

        with ExitStack() as stack:
            stack.enter_context(patch.object(NativeBound, "__call__",
                observe_bound(NativeBound.__call__, library, phases, records, probes.state)))
            stack.enter_context(patch.object(position.NormalPosition, "calculate",
                probes.calculations(position.NormalPosition.calculate, records)))
            stack.enter_context(patch.object(compact_cavity_optimizer, "_forward_points",
                probes.points(compact_cavity_optimizer._forward_points)))
            start = process_time_ns()
            result = partial(*args, **kwargs)
            audit["finalist_observed_cpu_ns"] = process_time_ns()-start
        return result

    def refine(*args, **kwargs):
        rank = v5_core.ranked_initial_nodes

        def priced_rank(scan):
            start = process_time_ns()
            nodes = rank(scan)
            audit["rank_cpu_ns"] = process_time_ns()-start
            audit["shortlist"] = [signature(node) for node in nodes[:3]]
            return nodes

        start = process_time_ns()
        with patch.object(v5_core, "ranked_initial_nodes", priced_rank), patch.object(race, "partial_fits", finalists):
            node, point, phase, trace = original(*args, **kwargs)
        totals = Counter()
        for item in records:
            totals.update(item.get("phases", {}))
        if not records or len(probes.models) != 6 or not audit.get("rank_cpu_ns"):
            raise ValueError("Expected actual scoped Gamma calls in all three two-phase finalists")
        audit.update(cold_observed_cpu_ns=process_time_ns()-start, winner=signature(node),
                     endpoint=point, reference=phase, trace=trace, probe_counts=probes.counts(), probe_rows=probes.rows,
                     phase_cpu_ns=dict(totals), kernel_stock_cpu_ns=sum(row["native_cpu_ns"] for row in records),
                     shadow_cpu_ns=probes.state["shadow_cpu_ns"], native_calls=records)
        raise ColdComplete

    with patch.object(race, "refine", refine):
        yield


def scientific(value):
    if isinstance(value, dict):
        return {str(key): scientific(item) for key, item in value.items() if key != "cpu_ns"}
    if hasattr(value, "tolist"):
        return scientific(value.tolist())
    if isinstance(value, (tuple, list)):
        return [scientific(item) for item in value]
    return value


def worker(root, case):
    from aperture_trial import archive_identity, read, write
    from empty_bootstrap import checked
    import unified_short_bootstrap as entry
    from prospective_0316_solver import worker as saved_worker
    from rescue_phase_prepare_trial import CONTROLS, FILES

    name, request_sha, inventory_sha = ASSIGNMENTS[case]
    staged = Path("/dev/shm") / name
    job, inventory = staged / "request.json", staged / "inventory.json"
    checked(job, request_sha)
    checked(inventory, inventory_sha)
    request = read(job)
    inputs = [request["native_file"], request["offer_file"], request["local_archive"]["root"],
              *request["local_libraries"].values()]
    if not all(Path(item).resolve(strict=True).is_relative_to(Path("/dev/shm")) for item in inputs):
        raise ValueError("The measurement can only use the sealed tmpfs inputs")
    control, control_sha = CONTROLS[case]
    checked(control / "joint-research-receipt.json", control_sha)
    binding = read(root / "binding.json")
    original = entry.publish_active
    audit = {}

    def active(args, *values, **options):
        from named_constrained_research import deny_waveform
        from leo.storage.short_window import ShortWindowReader
        identity = archive_identity(Path(request["local_archive"]["root"]))["snapshots_sha256"]
        if identity != request["local_archive"]["snapshots_sha256"]:
            raise ValueError("Causal snapshots no longer match the sealed request")
        args.named_survivor_finish = True
        args.direct_residual_figures = args.direct_orbit_figures = True
        with measure_cold(root / "diagnostic.so", audit), patch.object(ShortWindowReader, "__init__", deny_waveform):
            return original(args, *values, **options)

    if case == "DS30-0402":
        from prospective_0402_solver import SETTINGS
    else:
        from named_final_0374 import settings
        SETTINGS = settings()
    with patch.object(entry, "publish_active", active):
        try:
            saved_worker(job, "cumulative", root / "work", source_pins={k: binding["sources"][k] for k in FILES},
                         inventory_file=inventory, **SETTINGS)
        except ColdComplete:
            pass
        else:
            raise ValueError("No cold result available")
    reference = read(control / "joint-research-receipt.json")
    audit.update(control_sha256=control_sha, matched_archived_cold_trace=(
        scientific(audit["trace"]) == scientific(reference["route_details"]["cold"])))
    write(root / "audit.json", scientific(audit))
    if not audit["matched_archived_cold_trace"]:
        raise ValueError("Cold scientific trace changed")


def launch(root, case):
    from aperture_trial import RELEASE, write
    from full_short_physical import environment
    from rescue_phase_prepare_trial import FILES
    from short_raw_diagnostic import measure

    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use fresh tmpfs output")
    root.mkdir()
    names = (*FILES, Path(__file__).name, "cold-kernel-price-protocol.md")
    write(root / "binding.json", dict(case=case, base=BASE, request_sha256=ASSIGNMENTS[case][1],
        inventory_sha256=ASSIGNMENTS[case][2], sources={name: sha256((HERE/name).read_bytes()).hexdigest() for name in names}))
    (root / "tmp").mkdir()
    env = environment(root / "tmp")
    env["TMPDIR"] = str(root / "tmp")
    command = ["/usr/bin/timeout", "--kill-after=2s", "60s", RELEASE / "venv/bin/python", "-IB",
               __file__, "worker", root, case]
    timing = measure(command, env, root / "output")
    write(root / "clock.json", dict(timing=timing, command=list(map(str, command))))
    if timing["exit_code"]:
        raise RuntimeError(timing["stderr_tail"])


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("launch", "worker"))
    parser.add_argument("root", type=Path)
    parser.add_argument("case", choices=ASSIGNMENTS)
    args = parser.parse_args()
    {"launch": launch, "worker": worker}[args.operation](args.root, args.case)
