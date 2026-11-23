"""Measure the incumbent and reduced predictive factors on the same saved dense grid."""

import argparse
from contextlib import contextmanager
from copy import deepcopy
import gzip
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ARCHIVE = HERE / "measurements/full-family-amortized.json.gz"
ARCHIVE_SHA = "f2cf9e3546bd91273d03ba87b8c5fee54e4b80f25f3bb69f5ea2a700b8612ca3"
TOLERANCE = 1e-5
ARMS = ("c0", "fitted_c")


def verified(path, expected):
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != expected:
        raise ValueError("Unexpected archived dense control")
    return raw


def time_call(operation, *args):
    started = process_time_ns()
    result = operation(*args)
    return result, process_time_ns() - started


class GridComparison:
    def __init__(self):
        self.work = []
        self.baseline_scores = {}
        self.cell = None

    @contextmanager
    def evidence(self):
        import numpy as np
        from leo.presentation import localization_v3 as presentation
        from tools import algo08_position
        from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff
        from grid_predictive_reduction import reduced_predictive

        packet_builder = algo08_position.selected_packet
        grid_builder = presentation.sample_position_grid
        stock_objective = presentation.objective
        predictive_factor = handoff.predictive_factor

        def recorded_prediction(*args):
            if self.cell is None or "candidate" in self.cell:
                raise ValueError("Unexpected checked posterior call while measuring the grid")
            if len(self.work) % 2:
                (candidate, sizes), fast_cpu = time_call(reduced_predictive, *args)
                stock, stock_cpu = time_call(predictive_factor, *args)
            else:
                stock, stock_cpu = time_call(predictive_factor, *args)
                (candidate, sizes), fast_cpu = time_call(reduced_predictive, *args)
            self.cell.update(candidate=candidate["objective"], stock=stock["objective"])
            self.work.append(dict(arm=self.cell["arm"], point=self.cell["point"], stock_cpu_ns=stock_cpu,
                                  candidate_cpu_ns=fast_cpu, stock_objective=stock["objective"],
                                  candidate_objective=candidate["objective"], **sizes))
            return stock

        def objective(problem, context, x):
            original = stock_objective(problem, context, x)
            self.baseline_scores[self.cell["arm"], self.cell["point"]] = original
            if "candidate" not in self.cell:
                return original
            if context["families"]:
                raise ValueError("This comparison expects the original selected no-event likelihood")
            calculation = problem.calculate(x)
            elevation = float(np.sum(np.minimum(0, calculation["elevation"][problem.keep])**2)/4)
            curved = calculation["curved_negative_twice_elbo"]
            if float((curved + self.cell["stock"]) + 0. + elevation) != original:
                raise ValueError("The stock grid objective no longer consists of the captured terms")
            return float((curved + self.cell["candidate"]) + 0. + elevation)

        def grid(score, endpoints, **kwargs):
            def measured(arm, point):
                self.cell = dict(arm=arm, point=tuple(point))
                try:
                    return score(arm, point)
                finally:
                    self.cell = None

            start, wall = process_time_ns(), perf_counter_ns()
            with (patch.object(handoff, "predictive_factor", recorded_prediction),
                  patch.object(presentation, "objective", objective)):
                result = grid_builder(measured, endpoints, **kwargs)
            self.paired_grid_cpu_ns = process_time_ns() - start
            self.paired_grid_wall_ns = perf_counter_ns() - wall
            return result

        def packet(*args, **kwargs):
            with patch.object(presentation, "sample_position_grid", grid):
                result = packet_builder(*args, **kwargs)
            if hasattr(self, "packet"):
                raise ValueError("Expected just one selected evidence packet")
            self.packet = result
            return result

        with patch.object(algo08_position, "selected_packet", packet):
            yield

    def checked_grids(self, archive):
        from leo.contracts.digests import canonical_digest

        candidate = self.packet["position_grid"]
        stock = deepcopy(candidate)
        if not candidate["complete"] or candidate["planned_points"] != 179 or len(self.work) != 356:
            raise ValueError("Expected all 179 nodes and 356 fresh checked posterior predictions")
        maxima, changed, minima = {}, {}, {}
        for arm in ARMS:
            results = []
            for reference, new in zip(stock["points"], candidate["points"], strict=True):
                x = new["east_km"], new["north_km"]
                reference["scores"][arm] = self.baseline_scores[arm, x]
                results.append((reference["scores"][arm], new["scores"][arm]))
            maxima[arm] = max(abs(a-b) for a, b in results)
            changed[arm] = sum(a != b for a, b in results)
            amin = [min(range(len(results)), key=lambda i: results[i][j]) for j in range(2)]
            if maxima[arm] > TOLERANCE or amin[0] != amin[1]:
                raise ValueError("Reduced grid changes the tolerance or sampled minimizer")
            minima[arm] = amin[0]

        def digest(grid):
            return canonical_digest({k: v for k, v in grid.items() if k not in ("binding", "elapsed_seconds")})

        stock_digest = digest(stock)
        if stock_digest != archive["science"]["grid"]:
            raise ValueError("The reconstructed incumbent grid differs from the sealed control")
        return stock, candidate, dict(stock_grid_sha256=stock_digest, candidate_grid_sha256=digest(candidate),
            max_abs_error=maxima, scores_changed=changed, sampled_minima=minima, points=179)

    def timings(self):
        stock = sum(row["stock_cpu_ns"] for row in self.work)
        fast = sum(row["candidate_cpu_ns"] for row in self.work)
        # Both estimates still include common observer work, bound calculation
        # and the additional instrumentation. Kernel timers are the direct result.
        return dict(paired_grid_cpu_ns=self.paired_grid_cpu_ns, paired_grid_wall_ns=self.paired_grid_wall_ns,
                    stock_predictive_cpu_ns=stock, candidate_predictive_cpu_ns=fast,
                    shared_grid_and_measurement_cpu_ns=self.paired_grid_cpu_ns-stock-fast,
                    projected_stock_grid_cpu_ns=self.paired_grid_cpu_ns-fast,
                    projected_candidate_grid_cpu_ns=self.paired_grid_cpu_ns-stock,
                    candidate_breakdown_ns={key: sum(row[key] for row in self.work)
                        for key in ("whiten_cpu_ns", "bias_cpu_ns", "factor_cpu_ns")})


def png_receipts(packet, baseline_grid, candidate_grid):
    from leo.contracts.fast_standard_analysis import PLOTS
    from leo.presentation.fast_standard_analysis import render
    from PIL import Image

    result = {}
    for label, grid in (("stock", baseline_grid), ("candidate", candidate_grid)):
        output, cpu = time_call(lambda: render(dict(packet, position_grid=grid), title="DS30-0008"))
        if set(output) != set(PLOTS):
            raise ValueError("Expected all eight standard plots")
        decoded = {}
        for name in PLOTS:
            content = output[name]
            with Image.open(BytesIO(content)) as image:
                image.load()
                decoded[name] = dict(encoded=sha256(content).hexdigest(), size=image.size,
                                     pixels=sha256(image.convert("RGBA").tobytes()).hexdigest())
        result[label] = dict(renderer_cpu_ns=cpu, plots=decoded)
    result["same_decoded"] = {name: result["stock"]["plots"][name]["pixels"] ==
        result["candidate"]["plots"][name]["pixels"] for name in PLOTS}
    return result


def run(output):
    from full_family_amortized_trial import run as solve_once

    archive = json.loads(gzip.decompress(verified(ARCHIVE, ARCHIVE_SHA)))["runs"]["DS30-0008"]["control"]
    output.mkdir(exist_ok=False)
    comparison = GridComparison()
    path = output/"dense.json"
    solve_once("DS30-0008", "control", path, evidence_context=comparison.evidence)
    fitted = json.loads(path.read_bytes())
    for field in ("arms", "owners", "selected_rows", "objective_replay", "status", "reason", "grid_points"):
        if fitted[field] != archive[field]:
            raise ValueError(f"Dense archived control differs at {field}")
    for field in ("support", "finish", "signed", "decision", "reason", "exterior"):
        if [row.get(field) for row in fitted["attempts"]] != [row.get(field) for row in archive["attempts"]]:
            raise ValueError(f"Dense archived qualification differs at {field}")
    if fitted["science"]["path"] != archive["science"]["path"]:
        raise ValueError("The original optimizer paths changed")
    original_grid, proposed_grid, checks = comparison.checked_grids(archive)
    result = dict(solution=fitted, checks=checks, timings=comparison.timings(), nodes=comparison.work,
                  archive_sha256=ARCHIVE_SHA,
                  archived_evidence_cpu_s=archive["attempts"][0]["standard_evidence_clocks"]["cpu_s"],
                  archived_predictive_cpu_ns=archive["posterior_grid_handoff"]["predictive_kernel_cpu_ns"],
                  archived_curved_cpu_ns=archive["posterior_grid_handoff"]["curved_cpu_ns"],
                  stock_grid=original_grid, candidate_grid=proposed_grid)
    with (output/"checked-grids.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    images = png_receipts(comparison.packet, original_grid, proposed_grid)
    with (output/"png-check.json").open("x") as stream:
        json.dump(images, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=lambda path: Path(path).resolve())
    run(parser.parse_args().output)
