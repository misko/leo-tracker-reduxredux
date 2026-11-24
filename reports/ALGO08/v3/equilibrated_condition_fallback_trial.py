"""Measure the unmodified native and audited dense fallback on four saved calls."""

import argparse
from collections import Counter
import ctypes as ct
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
ROOT = Path("/tmp/leo-algo08v2-2x-bench")
NATIVE = "c649042b2a5ddf7890177d84b302a19edcf7a662aea16c18cb177317ccba818b"
THREADS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS")
CAPTURES = {
    "0008": "9861025ec7b0ee0ddeadab2fc161d4b8f2261e0f0cae5395b23aa3fa15ec3996",
    "south": "b83280f71374946ff21f489479fa03cd1a53331203c98438e3ed7b421aaa3b19",
}
PINS = {
    "ds30_width": ("0008", "sample-02.npz", "d26dec15aa99c6826af801993e6bdaa8f53e703e813ff475cde72f066c6d8f73", (4082, 242), "fallback_unsupported"),
    "ds30_fixed_control": ("0008", "sample-01.npz", "23a0d7693fd39cd5acf3e17f62eada46687019d86cf20df6e780b2277d4443d6", (4522, 255), "activated"),
    "south_condition": ("south", "sample-02.npz", "da78a84466a178ae50570257f8fa458394361d962ddd23b37200ace98ff49333", (4122, 104), "fallback_ill_conditioned"),
    "south_fixed_control": ("south", "sample-00.npz", "33338a344cde41bf2444a22dc34a9ca95b1ea91c7de20dd2c402684008b9b04e", (4122, 103), "activated"),
}


def clock(start):
    return dict(cpu_ns=process_time_ns() - start[0], wall_ns=perf_counter_ns() - start[1])


def now():
    return process_time_ns(), perf_counter_ns()


def checked(path, pin):
    blob = path.read_bytes()
    if sha256(blob).hexdigest() != pin:
        raise ValueError(f"Expected the original saved file: {path}")
    return blob


def measured_native(native):
    work = Counter()

    def counted(method, call):
        def run(*args):
            start = process_time_ns()
            result = call(*args)
            work[method + "_ns"] += process_time_ns() - start
            work[method + "_calls"] += 1
            return result

        return run

    native.layout = counted("layout", native.layout)
    native.run = counted("native_run", native.run)
    return work


def condition_checks(native, call):
    """Observe the actual released LAPACKE Schur condition callback."""
    original = native.functions[-1]
    rows = []

    @ct.CFUNCTYPE(*[original.restype, *original.argtypes])
    def observed(layout, uplo, dimension, root, stride, norm, output):
        status = original(layout, uplo, dimension, root, stride, norm, output)
        value = ct.cast(output, ct.POINTER(ct.c_double)).contents.value
        rows.append(dict(dimension=dimension, norm=norm, rcond=value, status=status))
        return status

    old = native.addresses[-1]
    try:
        native.addresses[-1] = ct.cast(observed, ct.c_void_p)
        call()
    finally:
        native.addresses[-1] = old
    return dict(calls=len(rows), first=rows[0] if rows else None,
                minimum=min(rows, key=lambda state: state["rcond"]) if rows else None,
                last=rows[-1] if rows else None)


def compare(native, dense, sample, options, expected, reverse):
    import numpy as np
    from equilibrated_condition_fallback import DenseAlternative, exact_unsupported_layout

    control, stable, cached = (native() for _ in range(3))
    owners = dict(stock=control, stable=stable, cached_layout=cached)
    alternative = DenseAlternative(dense)
    stable.original = alternative
    patched, cache = exact_unsupported_layout(cached.__call__)
    work = {name: measured_native(owner) for name, owner in owners.items()}
    original = control(*sample, **options)
    control_checks = condition_checks(control, lambda: control(*sample, **options))
    before = now()
    patched(*sample, **options)
    activation_warm = clock(before)
    verified = DenseAlternative(dense, verify=True)
    verifier = native()
    verifier.original = verified
    verification_start = now()
    verification = verifier(*sample, **options)
    verification_clock = clock(verification_start)

    samples = []
    for index in range(3):
        order = ["stock", "stable", "cached_layout", "dense_oracle"]
        if expected == "activated":
            order.pop()
        if (index + reverse) % 2:
            order.reverse()
        record = {"order": order}
        for name in order:
            operation = patched if name == "cached_layout" else owners.get(name, dense)
            native_before = work.get(name, Counter()).copy()
            before = now()
            output = operation(*sample, **options)
            record[name] = clock(before)
            if name in work:
                record[name]["native"] = dict(work[name] - native_before)
            if name == "stable":
                if (output["precision_iterations"] != original["precision_iterations"]
                        or any(np.max(abs(np.asarray(output[key]) - np.asarray(value)), initial=0) > 1e-6
                               for key, value in original.items())):
                    raise ValueError("Stable dense call changed the original bounded-likelihood readout")
            elif any(not np.array_equal(output[key], value) for key, value in original.items()):
                raise ValueError("The original dense or released route changed")
        samples.append(record)

    if any(owner.counts[expected] != owner.counts["calls"] for owner in owners.values()):
        raise ValueError("The original native route changed")
    if any(not np.array_equal(verification[key], value) if expected == "activated" else
           np.max(abs(np.asarray(verification[key]) - np.asarray(value)), initial=0) > 1e-6
           for key, value in original.items()):
        raise ValueError("Diagnostic alternative violated release readouts")
    all_events = verified.events
    extremes = {key: (min if key.endswith("condition") else max)(row[key] for row in all_events if key in row)
                for key in sorted({key for row in all_events for key in row})}
    result = dict(
        output_coefficient_delta=float(np.max(abs(verification["coefficient"] - original["coefficient"]))),
        output_residual_delta=float(np.max(abs(verification["conditional_residual_hz"] - original["conditional_residual_hz"]))),
        output_ELBO_delta=float(abs(verification["negative_twice_elbo"] - original["negative_twice_elbo"])),
        changes_in_convergence=float(abs(verification["final_log_precision_change"] - original["final_log_precision_change"])),
        original_updates=original["precision_iterations"], audited_updates=verification["precision_iterations"],
        condition_checks=control_checks, native_work={key: dict(value) for key, value in work.items()},
        native_counts={key: dict(value.counts) for key, value in owners.items()}, layout_cache=dict(cache),
        stable_counts=dict(alternative.counts), stable_retries=alternative.error, verified_counts=dict(verified.counts),
        verified_retries=verified.error, factor_checks=extremes, first_factor=all_events[0] if all_events else None,
        verification_clock=verification_clock, layout_first_call=activation_warm,
        repeated=samples, medians={name: int(median(row[name]["cpu_ns"] for row in samples)) for name in order},
    )
    for owner in (*owners.values(), verifier):
        owner.clear()
    return result


def run(output):
    if output.exists() or output.parent.resolve() != output.parent:
        raise ValueError("Use a fresh local output file")
    if (os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) < 15
            or subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip() != "best-effort: prio 7"
            or any(os.getenv(key) != "1" for key in THREADS)):
        raise ValueError("Use the shared low-priority one-core configuration")
    begin = now()
    sys.path.insert(0, str(RELEASE/"src"))
    import numpy as np
    from leo.analysis.localization_v3.hierarchical import hierarchical_bound
    from leo.analysis.localization_v4.native_bound import NativeBound

    path = RELEASE/"assets/native/native_bound.so"
    checked(path, NATIVE)
    directories = {name: ROOT/("dense-likelihood-capture-" + name) for name in CAPTURES}
    captures = {key: json.loads(checked(directories[key]/"capture.json", pin)) for key, pin in CAPTURES.items()}
    result = dict(setup=clock(begin), source_native=NATIVE, catalogue_captures=CAPTURES, panels={}, census={})
    for key, value in captures.items():
        counts, cost = Counter(), Counter()
        for row in value["groups"]:
            counts[row["outcome"]] += row["calls"]
            cost[row["outcome"]] += row["cpu_ns"]
        result["census"][key] = dict(counts=counts, cpu_ns=cost)
    try:
        probe = NativeBound(path)
        result["provider"] = probe.provider_info
        probe.clear()
        for idx, (panel, (source, filename, pin, shape, route)) in enumerate(PINS.items()):
            start = now()
            with np.load(BytesIO(checked(directories[source]/filename, pin)), allow_pickle=False) as data:
                sample = tuple(data[key] for key in ("raw", "features", "sigma", "groups"))
                options = {key: data[key] for key in data if key not in ("raw", "features", "sigma", "groups")}
            if sample[1].shape != shape or captures[source]["samples"][filename]["caller"] not in ("position", "history_position"):
                raise ValueError("Expected a saved original numerical arm")
            loaded = clock(start)
            result["panels"][panel] = dict(pin=pin, shape=shape, route=route, load=loaded,
                **compare(lambda: NativeBound(path), hierarchical_bound, sample, options, route, idx % 2))
    finally:
        use = resource.getrusage(resource.RUSAGE_SELF)
        result["total"] = clock(begin)
        result["resource"] = dict(input_blocks=use.ru_inblock, major_faults=use.ru_majflt, max_rss_kib=use.ru_maxrss)
        result["sources"] = {name: sha256((HERE/name).read_bytes()).hexdigest() for name in (
            Path(__file__).name, "equilibrated_condition_fallback.py", "equilibrated-condition-fallback-protocol.md")}
        with output.open("x") as stream:
            json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    run(cli.parse_args().output)
