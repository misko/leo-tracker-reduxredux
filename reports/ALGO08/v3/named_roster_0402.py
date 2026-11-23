"""Profile the original named DS30-0402 selection on the already sealed packet."""

import argparse
from collections import defaultdict
from contextlib import contextmanager
from functools import partial, wraps
from hashlib import sha256
from pathlib import Path
import sys
from time import process_time_ns
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from cross_roster_0155 import ARMS, brief, capture, pinned, row_data
from named_roster_0155 import launch, profile_named, same_science, seal_results
from prospective_0402_solver import ARCHIVE_SHA, CUTOFF, SETTINGS, invoke, refs


STAGE = Path("/dev/shm/leo-v3-saved-0402-pair-01")
BASELINE = STAGE.with_name("leo-v3-saved-0402-score-02.json")
PINS = dict(request="a2d730f64833eafd096877650e24b5c250b3bcfbef69d6bb5a44b70f0cbf1274",
            stock="865eb04161117f948ad3bccb6f6bfd3d5442acdc7d1edefcf03a65d441994633",
            scored="9ae7020102cad2356ce7b8beaf5799e421d750bde358dd486b6130558334ddd4")


def bound_route(before, after):
    routes = [name for name in before if (name == "activated" or name.startswith("fallback_"))
              and after[name] == before[name] + 1]
    if len(routes) != 1 or after["calls"] != before["calls"] + 1:
        raise ValueError("Expected one original likelihood activation or fallback")
    return routes[0]


class BoundTrace:
    def __init__(self, bound, ledger, timer=process_time_ns):
        self.bound, self.ledger, self.timer = bound, ledger, timer
        self.rows = defaultdict(lambda: dict(calls=0, cpu_ns=0, updates=0, max_updates=0, max_cpu_ns=0))

    def instrument(self):
        cls = type(self.bound)
        original = cls.__call__

        @wraps(original)
        def measured(owner, *args, **kwargs):
            if owner is not self.bound:
                return original(owner, *args, **kwargs)
            before, start = owner.counts.copy(), self.timer()
            result = original(owner, *args, **kwargs)
            duration = self.timer() - start
            path = bound_route(before, owner.counts)
            n, p = args[1].shape
            groups = len(result["noise_precision"])
            updates = int(result["precision_iterations"])
            bucket = self.rows[self.ledger.active, path, n, p, groups]
            bucket["calls"] += 1
            bucket["cpu_ns"] += duration
            bucket["updates"] += updates
            bucket["max_updates"] = max(bucket["max_updates"], updates)
            bucket["max_cpu_ns"] = max(bucket["max_cpu_ns"], duration)
            return result

        return patch.object(cls, "__call__", measured)

    def receipt(self):
        return [dict(scope=scope, route=route, observations=n, columns=p, groups=groups, **row)
                for (scope, route, n, p, groups), row in sorted(self.rows.items())]


def trial_record(result):
    return dict(paired_valid=result["paired_valid"], replacements=result["replacements"],
                constrained=result["constrained_refinement_attempted"],
                arms={arm: dict(loss=row["corrected_selection_loss"],
                                phase_change_s=row["final_phase_change_s"], rf_rms_hz=row["RMS_hz"],
                                refits=len(row["history"]), failed_tracks=sum(
                                    not gate["compatible"] for gate in row["gates"]["tracks"] + row.get("linear_gates", [])))
                      for arm, row in result["arms"].items()})


@contextmanager
def extra_trace(seen, ledger, bound):
    from leo.analysis.localization_v3 import family_cavity
    from tools.pipeline_eval.variants import v5_screen_winner

    screen, cavity = v5_screen_winner.screen_nodes, family_cavity.cavity_policy
    likelihood = BoundTrace(bound, ledger)

    def screened(scan, nodes, metrics):
        answer = screen(scan, nodes, metrics)
        seen["screened_nomination"] = dict(metrics)
        return answer

    def offered(*args):
        result = cavity(*args)
        if result["status"] == "complete":
            seen["cavity"] = dict(accepted=result["accepted"], trials=[trial_record(row) for row in result["trials"]],
                                  gain=result["selection_gain"], penalty=result["search_penalty"],
                                  null_objective_replay_differences=result["null_objective_replay_differences"])
        return result

    with (patch.object(v5_screen_winner, "screen_nodes", screened),
          patch.object(family_cavity, "cavity_policy", offered), likelihood.instrument()):
        try:
            yield
        finally:
            seen["likelihood"] = likelihood.receipt()
            seen["bound_counts"] = bound.counts.copy()


def verify_selected(result, screened, expected):
    from leo.contracts.digests import canonical_digest

    names = ("ranks", "screen_c0_scores", "winning_rank", "completed_c0_score", "early_fits", "finish_fits",
             "initial_phase_fits", "fallback")
    same_science({key: screened[key] for key in names}, expected["receipt"]["screened_nomination"])
    if screened["winning_rank"] != 1 or any(len(result["rows"][a]) != 4821 for a in ARMS):
        raise ValueError("The original rank-one decision or ordered support count changed")
    same_science({"objective_replay": result["packet_replay"]}, expected["solve"])
    ctx = result["context"]
    arms = {}
    for arm, original in ctx["saved"]["policy_arms"].items():
        rows = result["rows"][arm]
        roles = {role: sum(row[2] == role for row in rows) for role in ("conditional", "predictive")}
        same_science({arm: roles}, expected["selected_roles"])
        arms[arm] = dict(**brief(ctx, arm, original), roles=roles,
                         ordered_owner_sha256=canonical_digest(rows),
                         ordered_likelihood_sha256=canonical_digest(row_data(ctx, arm)))
    return dict(screened_nomination=screened, selection_clock=result["selection_clock"],
                capture_clock=result["capture_clock"], arms=arms, objective_replay=result["packet_replay"],
                phase_history_sha256=result["phase_history"], phase_forecast_sha256=result["forecast"])


def run(root):
    import empty_bootstrap as boot
    from dense_geographic_trial import host

    machine = host()
    if root.absolute() != root.resolve() or not root.is_relative_to("/dev/shm"):
        raise ValueError("The saved roster diagnostic requires a fresh tmpfs destination")
    root.mkdir()
    runtime = boot.load_runtime()
    from aperture_trial import write
    from leo.contracts.digests import canonical_digest

    job = STAGE / "request.json"
    request = pinned(job, PINS["request"])
    archived = pinned(BASELINE, PINS["scored"])["runs"]["stock"]
    expected = pinned(STAGE / "stock/joint-research-receipt.json", PINS["stock"])
    archive = STAGE / "tle"
    if (Path(request["local_archive"]["root"]).resolve() != archive or request["causal_cutoff_utc_ns"] != CUTOFF
            or Path(request["native_file"]).resolve() != STAGE / "named-detections.json"
            or canonical_digest({row.path.name: row.sha256 for row in refs(archive)}) != ARCHIVE_SHA):
        raise ValueError("Expected the same sealed tmpfs inputs and causal cutoff used in the named replay")

    observed = {}
    selection = partial(capture, root, "stock", archived, expected, job=job, invoke_job=invoke, cutoff=CUTOFF)
    result, timings = profile_named(runtime, selection, extension=partial(extra_trace, observed))
    source_hashes = {name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
        Path(__file__).name, "named_roster_0155.py", "cross_roster_0155.py", "named-roster-0402-protocol.md")}
    accounting = dict(machine=machine, **timings, **observed, bindings=PINS, source_hashes=source_hashes,
                      native_sha256=SETTINGS["native_sha"], archive_sha256=ARCHIVE_SHA,
                      plot_calls=0, grid_calls=0, waveform_calls=0)
    seal_results(write, root, accounting, lambda: verify_selected(result, observed["screened_nomination"], expected))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "launch"))
    parser.add_argument("root", type=Path)
    options = parser.parse_args()
    if options.mode == "run":
        run(options.root)
    else:
        launch(options.root, stage=STAGE, driver=__file__)
