"""Account for the named solver through its authentic selected-evidence port."""

import argparse
from collections import defaultdict
from contextlib import ExitStack, contextmanager
from cProfile import Profile
from functools import wraps
from hashlib import sha256
import json
from pathlib import Path
from pstats import Stats
import sys
from time import process_time_ns
from unittest.mock import patch

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from cross_roster_0155 import ARMS, BASELINE, BASELINE_SHA, RESEARCH, REQUEST_SHA, STAGE, brief, capture, pinned, row_data


HERE = Path(__file__).resolve().parent
CROSS = STAGE.with_name("leo-v3-cross-roster-0155-01") / "captured-contexts.json"
CROSS_SHA = "52c26d8b414059f848374bac4bb6fb130ec22003f68e7e1cd16465bb8b0297a9"


class Ledger:
    """Charge nested CPU to the innermost named scope once."""

    def __init__(self, timer=process_time_ns):
        self.timer = timer
        self.stack = []
        self.amounts = defaultdict(lambda: dict(calls=0, inclusive_cpu_ns=0, exclusive_cpu_ns=0))

    @contextmanager
    def scope(self, name):
        children = [0]
        self.stack.append(children)
        start = self.timer()
        try:
            yield
        finally:
            duration = self.timer() - start
            self.stack.pop()
            if self.stack:
                self.stack[-1][0] += duration
            row = self.amounts[name]
            row["calls"] += 1
            row["inclusive_cpu_ns"] += duration
            row["exclusive_cpu_ns"] += duration - children[0]

    def measure(self, module, name, label):
        original = getattr(module, name)

        @wraps(original)
        def measured(*args, **kwargs):
            with self.scope(label):
                return original(*args, **kwargs)

        return patch.object(module, name, measured)


def profile_receipt(profile):
    def record(key, row):
        path, line, name = key
        primitive, calls, own, total, callers = row
        return dict(path=path, line=line, function=name, primitive=primitive, calls=calls,
                    exclusive_wall_s=own, inclusive_wall_s=total,
                    callers=[dict(path=k[0], line=k[1], function=k[2], calls=v[0], inclusive_wall_s=v[3])
                             for k, v in sorted(callers.items(), key=lambda item: item[1][3], reverse=True)[:8]])

    measured = Stats(profile)
    records = set()
    for index in (2, 3):
        records.update(sorted(measured.stats, key=lambda key: measured.stats[key][index], reverse=True)[:110])
    return dict(exclusive_wall_s=measured.total_tt, function_calls=measured.total_calls,
                rows=[record(k, measured.stats[k]) for k in sorted(records, key=lambda k: (-measured.stats[k][2], k))])


def same_science(actual, archived):
    from leo.application.localization_v3_engine import _json_value

    for key, value in actual.items():
        if json.loads(json.dumps(value, default=_json_value, allow_nan=False)) != archived[key]:
            raise ValueError(f"Named selected science changed at {key}")


def verify_result(result, archived):
    from leo.contracts.digests import canonical_digest

    ctx = result["context"]
    common = dict(model=ctx["model"], noise_sha256=ctx["scan"].fixed_window_noise_sha256,
                  phase_history_sha256=result["phase_history"], phase_forecast_sha256=result["forecast"],
                  objective_replay=result["packet_replay"], predictive_entries_sha256=canonical_digest(ctx["entries"]))
    same_science(common, archived)
    arms = {}
    for arm in ARMS:
        p, _ = ctx["problems"][arm]
        arms[arm] = dict(**brief(ctx, arm, ctx["saved"]["policy_arms"][arm]),
                         ordered_public_rows_sha256=canonical_digest(result["rows"][arm]),
                         ordered_row_and_likelihood_sha256=canonical_digest(row_data(ctx, arm)),
                         hardware_design_sha256=sha256(p.hardware.tobytes()).hexdigest(),
                         receiver_smooth_design_sha256=sha256(p.smooth.tobytes()).hexdigest())
        same_science(arms[arm], archived["arms"][arm])
    return dict(**common, arms=arms, selection_clock=result["selection_clock"], capture_clock=result["capture_clock"])


def seal_results(write, root, accounting, verify):
    write(root / "roster.json", accounting)
    write(root / "science.json", verify())


def run(root):
    import empty_bootstrap as boot
    from dense_geographic_trial import host

    machine = host()
    if root.absolute() != root.resolve() or not root.is_relative_to("/dev/shm"):
        raise ValueError("The saved 0155 diagnostic requires a fresh tmpfs destination")
    root.mkdir()
    runtime = boot.load_runtime()
    from aperture_trial import write
    from leo.analysis.localization_v3 import conservative_recovery, family_cavity, history_policy, signed_context
    from tools import algo08_position as position
    from tools.pipeline_eval.variants import v5_core, v5_screen_winner, v5_tiled_salvage

    request = pinned(STAGE / "request.json", REQUEST_SHA)
    archived = pinned(BASELINE, BASELINE_SHA)["runs"]["stock"]
    expected = pinned(STAGE / "stock/joint-research-receipt.json", RESEARCH["stock"])
    crossed = pinned(CROSS, CROSS_SHA)["contexts"]["stock"]
    if Path(request["local_archive"]["root"]) != STAGE / "tle":
        raise ValueError("Expected the original sealed tmpfs archive")

    profile = Profile()
    ledger = Ledger()
    prepare, infer = position.prepare_native_scan, v5_core.infer
    trace = dict(preparations=0, selected=0)

    def prepare_original(*args, **kwargs):
        trace["preparations"] += 1
        if trace["preparations"] != 1:
            raise ValueError("Unexpected retry while profiling the named 0155 route")
        trace["start_ns"] = process_time_ns()
        profile.enable()
        with ledger.scope("prepare_native_scan"):
            return prepare(*args, **kwargs)

    def select(prepared, region, bound, stage_s, *, selected_evidence, **kwargs):
        def seal(*values):
            profile.disable()
            trace["selected"] += 1
            trace["selected_ns"] = process_time_ns()
            trace["original_stage_wall_s"] = stage_s.copy()
            return selected_evidence(*values)

        with ExitStack() as active_route:
            for module, name, label in (
                (v5_core, "scan_context", "scan_context"),
                (v5_core, "ranked_initial_nodes", "ranked_initial_nodes"),
                (v5_core, "fit_initial_nodes", "ordinary_initial_fallback"),
                (v5_screen_winner, "screen_nodes", "screened_initial_fit"),
                (conservative_recovery, "conservative_recovery", "conservative_recovery"),
                (conservative_recovery, "fit_and_gate", "conservative_fit_and_gate_executed"),
                (conservative_recovery, "salvage", "conservative_salvage"),
                (conservative_recovery, "repaired_fit", "conservative_salvage_fit"),
                (conservative_recovery, "extend_associations", "conservative_extension"),
                (v5_tiled_salvage, "fine_alternatives", "salvage_fine_alternatives"),
                (v5_tiled_salvage, "coarse_scores", "salvage_coarse_scores"),
                (history_policy, "history_policy", "history_policy"),
                (history_policy, "history_fit", "history_curved_policy"),
                (history_policy, "linear_refit", "history_linear_refit"),
                (signed_context, "signed_context", "signed_context"),
                (signed_context, "refit", "signed_context_refit"),
                (family_cavity, "nominate_families", "nominate_families"),
                (family_cavity, "cavity_policy", "cavity_policy"),
                (family_cavity, "fit_configuration", "cavity_fit_configuration"),
            ):
                active_route.enter_context(ledger.measure(module, name, label))
            return infer(prepared, region, bound, stage_s, selected_evidence=seal, **kwargs)

    with ExitStack() as scope:
        scope.enter_context(patch.object(boot, "load_runtime", return_value=runtime))
        scope.enter_context(patch.object(position, "prepare_native_scan", prepare_original))
        scope.enter_context(patch.object(v5_core, "infer", select))
        scope.enter_context(ledger.measure(position, "_prepared_values", "convert_prepared"))
        try:
            result = capture(root, "stock", archived, expected)
        finally:
            profile.disable()

    if trace["selected"] != 1 or len(ledger.stack):
        raise ValueError("The bounded capture must finish at precisely one selected-evidence call")
    compute_ns = trace.pop("selected_ns") - trace.pop("start_ns")
    charged = sum(row["exclusive_cpu_ns"] for row in ledger.amounts.values())
    trace["compute_cpu_ns"] = compute_ns
    trace["unattributed_cpu_ns"] = compute_ns - charged
    accounting = dict(machine=machine, trace=trace, ledger=dict(ledger.amounts), profile=profile_receipt(profile),
                      bindings=dict(request=REQUEST_SHA, stock_pair=BASELINE_SHA, stock_selected=RESEARCH["stock"],
                                    cross_roster=CROSS_SHA, driver=sha256(Path(__file__).read_bytes()).hexdigest(),
                                    protocol=sha256((HERE / "named-roster-0155-protocol.md").read_bytes()).hexdigest()),
                      plot_calls=0, grid_calls=0, waveform_calls=0)
    seal_results(write, root, accounting, lambda: verify_result(result, crossed))


def launch(root):
    from aperture_trial import RELEASE, write
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    under = root.with_name(root.name + "-scratch")
    if root.absolute() != root.resolve() or not root.is_relative_to("/dev/shm"):
        raise ValueError("The saved 0155 diagnostic requires a fresh tmpfs destination")
    under.mkdir()
    env = environment(STAGE)
    env["TMPDIR"] = str(under)
    env["MPLCONFIGDIR"] = str(under)
    clock = measure([RELEASE / "venv/bin/python", "-IB", __file__, "run", root], env, root)
    write(root.with_name(root.name + "-clock.json"), clock)
    if clock["exit_code"]:
        raise RuntimeError("The bounded solver exited before reaching selected evidence")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "launch"))
    parser.add_argument("root", type=Path)
    options = parser.parse_args()
    (run if options.mode == "run" else launch)(options.root)
