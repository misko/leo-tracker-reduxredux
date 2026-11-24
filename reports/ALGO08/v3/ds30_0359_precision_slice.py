"""Time two predictive kernels on the same actual saved grid inputs."""

import argparse
from collections import Counter
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]

from ds30_0359_cairo_saved import JOB_PIN, READY, READY_PIN


ROOT = Path("/dev/shm/leo-v3-0359-composed-saved-result01")
ADMISSION_PIN = "a37356faa7f27d355edbd60141bccc9156ddac5a106699cfb3f643e74ca43842"
PAIR = Path("/dev/shm/leo-v3-0359-predictive-grid-result01/paired-grid.json")
PAIR_PIN = "f81614a716b22e9e9d1e9fdce9712dbb8bd57588fdd466180d3c5a1cac9db502"
ORDINALS = frozenset(range(0, 48, 3))
GRID_CALLS = 356
OBJECTIVE_TOL = 1e-5
RESIDUAL_TOL = 1e-8


class SliceComplete(Exception):
    """Both arms yielded all prespecified timings."""


def paired_clock(operation):
    started = perf_counter_ns(), process_time_ns()
    result = operation()
    return result, dict(wall_ns=perf_counter_ns()-started[0], cpu_ns=process_time_ns()-started[1])


def run(output):
    import empty_bootstrap as boot
    from aperture_trial import write
    from reports.ALGO08.v3 import ds30_0163_combined as original

    started = boot.now()
    past = json.loads(boot.checked(PAIR, PAIR_PIN))["calls"]
    if len(past) != GRID_CALLS:
        raise ValueError("The archived grid control is incomplete")
    order = list(dict.fromkeys(record["arm"] for record in past))
    if len(order) != 2:
        raise ValueError("Both calibration arms are required")
    admission = json.loads(boot.checked(ROOT / "admission.json", ADMISSION_PIN))
    output.mkdir(mode=0o700)
    (output / "routed").mkdir()
    write(output / "admission.json", admission)
    counts, records = Counter(), []
    active_arm = None
    original_load = boot.load_runtime
    before_slice = None

    def load():
        runtime = original_load()
        from grid_predictive_reduction import reduced_predictive
        from grid_predictive_precision import predictive_precision
        from leo.presentation import localization_v3 as presentation
        from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff
        import numpy as np

        sample = presentation.sample_position_grid

        def observe(*args):
            if active_arm not in order:
                raise ValueError("Expected the original arm-scoped grid callback")
            ordinal = counts[active_arm]
            counts[active_arm] += 1

            def incumbent():
                return reduced_predictive(*args, include_residual=True)

            if ordinal not in ORDINALS:
                return incumbent()[0]

            def challenger():
                return predictive_precision(*args)

            candidate_first = (ordinal + order.index(active_arm)) % 2 == 1
            if candidate_first:
                candidate, fast = paired_clock(challenger)
                (control, sizes), stock = paired_clock(incumbent)
            else:
                (control, sizes), stock = paired_clock(incumbent)
                candidate, fast = paired_clock(challenger)
            row = [entry for entry in past if entry["arm"] == active_arm][ordinal]
            if (any(sizes[name] != row[name] for name in ("rows", "width", "biases", "prefix"))
                    or sizes["prefix"] != 0 or abs(row["candidate_objective"] - control["objective"]) > OBJECTIVE_TOL):
                raise ValueError("The incumbent did not replay the archived predictive operand scope")
            difference = abs(control["objective"] - candidate["objective"])
            residual = float(np.max(np.abs(control["residual"] - candidate["residual"])))
            normalization_equal = control["normalization_constant"] == candidate["normalization_constant"]
            records.append(dict(arm=active_arm, ordinal=ordinal, candidate_first=candidate_first,
                                incumbent=stock, precision=fast, objective_change=difference,
                                residual_change=residual, normalization_equal=normalization_equal,
                                **sizes))
            return control

        def grid(score, endpoints, **options):
            nonlocal before_slice

            def rated(arm, point):
                nonlocal active_arm
                active_arm = arm
                try:
                    value = score(arm, point)
                    if len(records) == len(ORDINALS) * len(order):
                        raise SliceComplete()
                    return value
                finally:
                    active_arm = None

            before_slice = boot.clock(started)
            with patch.object(handoff, "predictive_factor", observe):
                return sample(rated, endpoints, **options)

        stack.enter_context(patch.object(presentation, "sample_position_grid", grid))
        return runtime

    with ExitStack() as stack:
        stack.enter_context(patch.object(boot, "load_runtime", load))
        try:
            original.worker(output, job_root=READY, admission_pin=READY_PIN, job_pin=JOB_PIN)
        except SliceComplete:
            pass
        else:
            raise ValueError("Expected to stop before the publication boundary")

    cpu = {name: sum(row[name]["cpu_ns"] for row in records) for name in ("incumbent", "precision")}
    wall = {name: sum(row[name]["wall_ns"] for row in records) for name in cpu}
    bound = (cpu["incumbent"]-cpu["precision"]) * GRID_CALLS / len(records)
    qualified = all(row["objective_change"] <= OBJECTIVE_TOL and row["residual_change"] <= RESIDUAL_TOL
                    and row["normalization_equal"] for row in records)
    write(output / "slice.json", dict(
        qualified_slice=qualified, timing_gate_cpu_ns=500_000_000, full_grid_scaling_cpu_ns=bound,
        eligible_for_full_validation=qualified and bound >= 500_000_000,
        predicted_full_grid_calls=GRID_CALLS, ordinals=sorted(ORDINALS), checked_cpu_ns=cpu, checked_wall_ns=wall,
        controls=dict(admission_sha256=ADMISSION_PIN, paired_grid_sha256=PAIR_PIN,
                      staged_admission_sha256=READY_PIN, job_sha256=JOB_PIN),
        source_sha256={name: sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                       for name in (Path(__file__).name, "grid_predictive_precision.py",
                                    "grid_predictive_reduction.py", "ds30-0359-precision-slice-protocol.md")},
        cpu_before_grid=before_slice, diagnostic_through_cutoff=boot.clock(started), observed_calls=counts,
        records=records, published=False, waveform_reads=0, backing_archive_reads=0))


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
