"""Time the unrolled dense tangent on two authentic captured calibration arms."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import resource
from statistics import median
import subprocess
import sys
from time import perf_counter_ns, process_time_ns


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
CAPTURE = Path("/tmp/leo-algo08v2-2x-bench/dense-likelihood-capture-south")
CAPTURE_PIN = "b83280f71374946ff21f489479fa03cd1a53331203c98438e3ed7b421aaa3b19"
NATIVE = "c649042b2a5ddf7890177d84b302a19edcf7a662aea16c18cb177317ccba818b"
PINS = {
    "c0": ("sample-00.npz", "33338a344cde41bf2444a22dc34a9ca95b1ea91c7de20dd2c402684008b9b04e", 103, "activated"),
    "fitted_c": ("sample-02.npz", "da78a84466a178ae50570257f8fa458394361d962ddd23b37200ace98ff49333", 104, "fallback_ill_conditioned"),
}
THREADS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def checked(path, pin):
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != pin:
        raise ValueError(f"Expected the pinned saved native input {path}")
    return raw


def now():
    return process_time_ns(), perf_counter_ns()


def clock(start):
    cpu, elapsed = now()
    return dict(cpu_ns=cpu - start[0], wall_ns=elapsed - start[1])


def directions(features, prior_groups):
    import numpy as np

    u = features[:, [4, 6]].T
    u = u / np.max(abs(u), axis=1, keepdims=True)
    return 100 * u, (0.03 * u[:, :, None]) * (features * (prior_groups >= 0))


def run_arm(native, dense, observed, sample, options, expected_route, reverse):
    import numpy as np
    from gamma_forward_sensitivity import Forward

    y, u, sigma, groups = sample
    start = now()
    dy, du = directions(u, options["prior_groups"])
    direction_clock = clock(start)

    def released(response, design):
        before = native.counts.copy()
        result = native(response, design, sigma, groups, **options)
        routes = [name for name in native.counts if (name == "activated" or name.startswith("fallback_"))
                  and native.counts[name] != before[name]]
        (route,) = routes
        return result, route

    def perturb(axis, step):
        return released(y + step * dy[axis], u + step * du[axis])

    centre, route = released(y, u)
    original_dense = dense(*sample, **options)
    if route != expected_route or centre["precision_iterations"] != original_dense["precision_iterations"]:
        raise ValueError("The released base captured computation changed path or step count")
    repetitions = []
    for index in range(3):
        order = ("candidate", "stock") if (index + reverse) % 2 else ("stock", "candidate")
        record = {"order": order}
        for mode in order:
            start = now()
            if mode == "candidate":
                observer = Forward(dy, du)
                primal = observed(observer, *sample, **options)
            else:
                forward = [perturb(axis, 0.001) for axis in range(2)]
                difference = np.column_stack([(row[0]["residual"] - centre["residual"]) / 0.001
                                              for row in forward])
            record[mode] = clock(start)
        exact_primal = all(np.array_equal(np.asarray(primal[key]).view(np.uint8),
                                          np.asarray(original_dense[key]).view(np.uint8))
                           if isinstance(primal[key], np.ndarray) else primal[key] == original_dense[key]
                           for key in original_dense)
        if not exact_primal or not np.isfinite(observer.jacobian).all():
            raise ValueError("The derivative instrumentation changed the original dense recurrence")
        record["tangent"] = dict(observer.counts)
        record["tangent_ns"] = observer.derivative_ns
        record["stock_routes"] = [value[1] for value in forward]
        record["stock_updates"] = [value[0]["precision_iterations"] for value in forward]
        repetitions.append(record)

    # An independent smaller symmetric difference checks the tangent off-clock.
    symmetric, diagnostic_steps = [], []
    for axis in range(2):
        plus, minus = perturb(axis, 0.0001), perturb(axis, -0.0001)
        symmetric.append((plus[0]["residual"] - minus[0]["residual"]) / 0.0002)
        diagnostic_steps.append([(value[0]["precision_iterations"], value[1]) for value in (plus, minus)])
    central = np.column_stack(symmetric)
    derivative = observer.jacobian
    gradient = lambda jacobian: 2 * centre["residual"] @ jacobian
    return dict(
        input_shape=list(u.shape), noise_groups=len(np.unique(groups)), prior_groups=len(np.unique(options["prior_groups"][options["prior_groups"] >= 0])),
        native_route=route, stock_base_updates=centre["precision_iterations"], dense_updates=original_dense["precision_iterations"],
        dense_primal_exact=exact_primal, native_to_dense_residual_max=float(np.max(abs(centre["residual"] - primal["residual"]))),
        finite_difference_relative_error=(np.linalg.norm(derivative - difference, axis=0) / np.linalg.norm(difference, axis=0)).tolist(),
        centered_difference_relative_error=(np.linalg.norm(derivative - central, axis=0) / np.linalg.norm(central, axis=0)).tolist(),
        forward_gradient=gradient(difference).tolist(), centered_gradient=gradient(central).tolist(), tangent_gradient=gradient(derivative).tolist(),
        update_slack=min(abs(value - 1e-5) for value in observer.change), variance_clip_slack=observer.min_variance,
        central_iterations_and_routes=diagnostic_steps, direction_setup=direction_clock,
        medians=dict(stock_two_native_ns=int(median(row["stock"]["cpu_ns"] for row in repetitions)),
                     unrolled_with_primal_ns=int(median(row["candidate"]["cpu_ns"] for row in repetitions)),
                     tangent_only_ns=int(median(row["tangent_ns"] for row in repetitions))),
        repetitions=repetitions,
    )


def run(output):
    if output.exists() or output.parent.resolve() != output.parent:
        raise ValueError("Use a fresh local diagnostic path")
    if (os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) < 15
            or subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip() != "best-effort: prio 7"
            or any(os.getenv(name) != "1" for name in THREADS)):
        raise ValueError("Require the shared low-priority Gauss configuration")
    start = now()
    sys.path.insert(0, str(RELEASE/"src"))
    import numpy as np
    from gamma_forward_sensitivity import instrument
    from leo.analysis.localization_v3 import hierarchical
    from leo.analysis.localization_v4.native_bound import NativeBound

    capture = json.loads(checked(CAPTURE/"capture.json", CAPTURE_PIN))
    binary = RELEASE/"assets/native/native_bound.so"
    checked(binary, NATIVE)
    native = NativeBound(binary)
    observed = instrument(hierarchical.hierarchical_bound)
    audit = dict(setup=clock(start), capture=CAPTURE_PIN, native=NATIVE, provider=native.provider_info,
                 sources={name: sha256((HERE/name).read_bytes()).hexdigest() for name in (
                     Path(__file__).name, "gamma_forward_sensitivity.py", "gamma-forward-sensitivity-protocol.md")}, arms={})
    begin = now()
    masks = {}
    try:
        for arm, (filename, pin, width, route) in PINS.items():
            if capture["samples"][filename]["caller"] != "history_position":
                raise ValueError("Expected the originally captured history position")
            start = now()
            blob = checked(CAPTURE/filename, pin)
            with np.load(BytesIO(blob), allow_pickle=False) as payload:
                sample = tuple(payload[key] for key in ("raw", "features", "sigma", "groups"))
                options = {key: payload[key] for key in ("powers", "prior_groups", "prior_nu")}
            group_column = sample[1][:, 8]
            rf_owner = all(np.unique(group_column[sample[3] == group]).size == 1 for group in np.unique(sample[3]))
            if sample[1].shape != (4122, width) or rf_owner != (arm == "fitted_c"):
                raise ValueError("Captured RF calibration arm changed")
            masks[arm] = sample[2], sample[3], options["powers"]
            load = clock(start)
            result = run_arm(native, hierarchical.hierarchical_bound, observed, sample, options, route, arm != "c0")
            audit["arms"][arm] = dict(load=load, sha256=pin, **result)
        audit["same_sigma_groups_and_powers"] = [bool(np.array_equal(left, right))
                                              for left, right in zip(*masks.values(), strict=True)]
    finally:
        native.clear()
        use = resource.getrusage(resource.RUSAGE_SELF)
        audit["measurement"] = clock(begin)
        audit["resource"] = dict(input_blocks=use.ru_inblock, major_faults=use.ru_majflt, max_rss_kib=use.ru_maxrss)
        with output.open("x") as stream:
            json.dump(audit, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    run(cli.parse_args().output)
