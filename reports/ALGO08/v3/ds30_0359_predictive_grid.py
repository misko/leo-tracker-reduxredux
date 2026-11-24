"""Pair the original and reduced predictors within the current saved exact grid."""

import argparse
from contextlib import ExitStack, contextmanager
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

from ds30_0359_cairo_saved import BASE, JOB_PIN, PRIOR_PIN, READY, READY_PIN, digest, launch, read
from grid_predictive_reduction_trial import GridComparison

PROTOCOL = HERE / "ds30-0359-predictive-grid-protocol.md"
HANDOFF_PIN = "aa5d7ab17ce82e4bd64e463de0fddf710275634cf48675cf6076eeba6c184831"
PRESENTATION_PIN = "5dd6dbc63a4078e4b7fffcf10237d4f92429a1ea07d585eb3a49d0eca02cae2b"


def timed(operation, *args, **kwargs):
    start_cpu, start_wall = process_time_ns(), perf_counter_ns()
    value = operation(*args, **kwargs)
    return value, process_time_ns() - start_cpu, perf_counter_ns() - start_wall


class LivePair(GridComparison):
    @contextmanager
    def evidence(self):
        from empty_bootstrap import checked
        from grid_predictive_reduction import reduced_predictive
        from leo.presentation import localization_v3 as presentation
        from tools import algo08_position
        from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff
        import numpy as np

        checked(Path(handoff.__file__), HANDOFF_PIN)
        checked(Path(presentation.__file__), PRESENTATION_PIN)
        packet_builder, ordinary_factor = algo08_position.selected_packet, handoff.predictive_factor
        ordinary_objective = presentation.objective

        def pair(*args):
            if self.cell is None or "predictor" in self.cell:
                raise ValueError("Expected one genuine checked posterior per fresh arm-location")

            def baseline():
                return timed(ordinary_factor, *args)

            def candidate():
                return timed(reduced_predictive, *args, include_residual=True)

            if len(self.work) % 2:
                (reduced, sizes), reduced_cpu, reduced_wall = candidate()
                stock, stock_cpu, stock_wall = baseline()
            else:
                stock, stock_cpu, stock_wall = baseline()
                (reduced, sizes), reduced_cpu, reduced_wall = candidate()
            if stock["normalization_constant"] != reduced["normalization_constant"]:
                raise ValueError("The predictive normalization changed")
            self.cell["predictor"] = (stock["objective"], reduced["objective"])
            self.work.append(dict(arm=self.cell["arm"], point=self.cell["point"], stock_cpu_ns=stock_cpu,
                                  stock_wall_ns=stock_wall, candidate_cpu_ns=reduced_cpu, candidate_wall_ns=reduced_wall,
                                  stock_objective=stock["objective"], candidate_objective=reduced["objective"], **sizes))
            return reduced

        def objective(problem, context, x):
            calculate, outputs = problem.calculate, []

            def capture(position):
                value = calculate(position)
                outputs.append(value)
                return value

            with patch.object(problem, "calculate", capture):
                counterfactual = ordinary_objective(problem, context, x)
            original = counterfactual
            if "predictor" in self.cell:
                if context["families"] or len(outputs) != 1:
                    raise ValueError("Expected one captured likelihood with no family addition")
                calculated, = outputs
                observed, reduced = self.cell["predictor"]
                curved = calculated["curved_negative_twice_elbo"]
                elevation = np.sum(np.minimum(0, calculated["elevation"][problem.keep]) ** 2) / 4
                if float((curved + reduced) + 0. + elevation) != counterfactual:
                    raise ValueError("The published scalar changed its original term accumulation")
                original = float((curved + observed) + 0. + elevation)
            self.baseline_scores[self.cell["arm"], self.cell["point"]] = original
            return counterfactual

        def packet(*args, **kwargs):
            current_grid = presentation.sample_position_grid

            def grid(score, endpoints, **options):
                def measured(arm, point):
                    self.cell = dict(arm=arm, point=tuple(point))
                    try:
                        return score(arm, point)
                    finally:
                        self.cell = None

                with (patch.object(handoff, "predictive_factor", pair),
                      patch.object(presentation, "objective", objective)):
                    observed, self.paired_grid_cpu_ns, self.paired_grid_wall_ns = timed(
                        current_grid, measured, endpoints, **options)
                return observed

            with patch.object(presentation, "sample_position_grid", grid):
                result = packet_builder(*args, **kwargs)
            if hasattr(self, "packet"):
                raise ValueError("Expected one final selected packet")
            self.packet = result
            return result

        with patch.object(algo08_position, "selected_packet", packet):
            yield

    def paired_timings(self):
        result = self.timings()
        stock = sum(node["stock_wall_ns"] for node in self.work)
        reduced = sum(node["candidate_wall_ns"] for node in self.work)
        return result | dict(stock_predictive_wall_ns=stock, candidate_predictive_wall_ns=reduced,
                             shared_grid_and_measurement_wall_ns=result["paired_grid_wall_ns"]-stock-reduced)


def pins():
    return {"paired_grid_sources": {str(path.relative_to(ROOT)): digest(path) for path in (
        Path(__file__), PROTOCOL, HERE / "grid_predictive_reduction.py", HERE / "grid_predictive_reduction_trial.py",
        HERE / "ds30_0359_cairo_saved.py")}}


def worker(root):
    import empty_bootstrap as boot
    from aperture_trial import write
    from reports.ALGO08.v3 import ds30_0163_combined as original

    book = read(root / "admission.json")
    if book["paired_grid_sources"] != pins()["paired_grid_sources"] or book["protocol_sha256"] != digest(PROTOCOL):
        raise ValueError("The frozen paired grid source changed")
    previous = json.loads(boot.checked(BASE / "result.json", PRIOR_PIN))
    stock_grid = previous["jobs"]["routed"]["publication"]["sidecars"]["grid"]["scientific_sha256"]
    original_load, comparison = boot.load_runtime, LivePair()
    with ExitStack() as stack:
        def load():
            loaded = original_load()
            stack.enter_context(comparison.evidence())
            return loaded

        stack.enter_context(patch.object(boot, "load_runtime", load))
        original.worker(root, job_root=READY, admission_pin=READY_PIN, job_pin=JOB_PIN)
    ordinary, reduced, checks = comparison.checked_grids({"science": {"grid": stock_grid}})
    write(root / "paired-grid.json", dict(ordinary=ordinary, candidate=reduced, checks=checks,
                                          clocks=comparison.paired_timings(), calls=comparison.work))


def probe():
    from reports.ALGO08.v3 import ds30_0163_combined as original

    result = original.probe(job_root=READY, admission_pin=READY_PIN, job_pin=JOB_PIN)
    print(json.dumps(result | {"paired_grid_ready": callable(LivePair.evidence) and bool(pins())}))


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "worker", "probe"))
    cli.add_argument("root", type=Path, nargs="?")
    args = cli.parse_args()
    if args.action == "probe":
        probe()
    elif args.action == "worker":
        worker(args.root)
    else:
        launch(args.root, entry=Path(__file__), extra_sources=pins, protocol=PROTOCOL)
