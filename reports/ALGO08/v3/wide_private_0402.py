"""Capture and qualify wider private likelihood blocks on saved 0402."""

import argparse
from collections import Counter, defaultdict
from functools import wraps
from hashlib import sha256
import importlib.util
import os
from pathlib import Path
from statistics import median
import sys
from time import process_time_ns
from unittest.mock import patch

import numpy as np

HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

import paired_veto_0402 as veto
import stock_exact_gate_0402 as exact
from constrained_pair_veto import guard
from cross_roster_0155 import capture
from prospective_0402_solver import CUTOFF, invoke


MODE = "LEO_RESEARCH_PRIVATE_WIDTH_MODE"
SAMPLE_ROOT = "LEO_RESEARCH_PRIVATE_WIDTH_CAPTURE"
FITTED_ONLY = Path("/dev/shm/leo-v3-0402-fitted-first-scored01.json")
FITTED_SHA = "62adacb55c835b36ae45dc1027e108f66da57b2ca8bec17bbd58f42cee1b8422"
SOURCES = HERE.parents[2] / "tools/pipeline_eval/variants"


def load_wider():
    path = SOURCES / "algo08_private_width.py"
    spec = importlib.util.spec_from_file_location("study_private_width", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def topology(features, groups):
    """Reconstruct the C layout's exact nonzero support by ordered noise group."""
    _, g = np.unique(groups, return_inverse=True)
    support = np.zeros((int(g.max()) + 1, features.shape[1]), dtype=bool)
    np.logical_or.at(support, g, features != 0.)
    private = np.count_nonzero(support[:, support.sum(axis=0) == 1], axis=1)
    widths = np.count_nonzero(support, axis=1)
    maximum = int(private.max())
    slots = int(widths @ widths)
    reason = "other"
    if len(features) > 100_000 or features.shape[1] > 512 or len(support) > 2048:
        reason = "input_size"
    else:
        total = 0
        for private_width, width in zip(private, widths, strict=True):
            if private_width > 2:
                reason = "private_columns"
                break
            total += int(width) ** 2
            if total > 2_000_000:
                reason = "gram_slots"
                break
    return dict(maximum_private=maximum, shared=int(np.count_nonzero(support.sum(axis=0) > 1)),
                gram_slots=slots, per_group_private=[int(n) for n in private],
                reason=reason)


def compare_bound(original, wider):
    if original.keys() != wider.keys():
        raise ValueError("The alternative likelihood changed the original fields")
    differences = {}
    for key in original:
        left, right = np.asarray(original[key]), np.asarray(wider[key])
        if left.shape != right.shape or not np.isfinite(right).all():
            raise ValueError(f"Unsupported likelihood result at {key}")
        differences[key] = float(np.max(np.abs(left.astype(float) - right.astype(float)), initial=0.0))
        if left.dtype.kind in "biu" and differences[key]:
            return differences, False
    continuous = all(np.allclose(original[k], wider[k], rtol=1e-8, atol=1e-6) for k in original)
    return differences, bool(continuous and differences["negative_twice_elbo"] <= 1e-7
                             and differences["conditional_residual_hz"] <= 1e-6
                             and original["precision_iterations"] == wider["precision_iterations"])


class Captures:
    def __init__(self):
        self.rows = defaultdict(lambda: dict(calls=0, cpu_ns=0, updates=0))
        self.samples = {}

    def monitor(self, cls):
        original = cls.__call__

        @wraps(original)
        def measured(owner, raw, features, noise, groups, **options):
            count = owner.counts["fallback_unsupported"]
            started = process_time_ns()
            result = original(owner, raw, features, noise, groups, **options)
            elapsed = process_time_ns() - started
            if owner.counts["fallback_unsupported"] != count:
                key = (*features.shape, len(result["noise_precision"]))
                row = self.rows[key]
                row["calls"] += 1
                row["cpu_ns"] += elapsed
                row["updates"] += int(result["precision_iterations"])
                if key not in self.samples and len(self.samples) < 4:
                    args = tuple(np.array(x, copy=True, order="K") for x in (raw, features, noise, groups))
                    kwargs = {k: v.copy() if isinstance(v, np.ndarray) else v for k, v in options.items()}
                    self.samples[key] = (owner, args, kwargs, topology(features, groups))
            return result

        return patch.object(cls, "__call__", measured)

    def price(self, overlay, library):
        results = []
        for key, row in sorted(self.rows.items()):
            entry = dict(rows=key[0], columns=key[1], groups=key[2], **row)
            sample = self.samples.get(key)
            if sample is not None:
                owner, args, options, layout = sample
                stock, wide, clocks = None, None, dict(stock=[], wider=[])
                original = type(owner).__call__
                with overlay.expand_unsupported_layout(library) as outcomes:
                    candidate_call = type(owner).__call__
                    for order in (("stock", "wider"), ("wider", "stock"), ("stock", "wider")):
                        for label in order:
                            start = process_time_ns()
                            if label == "stock":
                                stock = original(owner, *args, **options)
                            else:
                                wide = candidate_call(owner, *args, **options)
                            clocks[label].append(process_time_ns() - start)
                    counts = outcomes.copy()
                diffs, agrees = compare_bound(stock, wide)
                stock_ns, wider_ns = (median(clocks[k]) for k in ("stock", "wider"))
                entry.update(topology=layout, median_stock_cpu_ns=stock_ns, median_wider_cpu_ns=wider_ns,
                             timing=clocks, wider_counts=counts, agreement=agrees,
                             max_abs_differences=diffs,
                             argument_sha256=[sha256(a.tobytes()).hexdigest() for a in args])
            results.append(entry)
        return results


def capture_worker(output, runtime, boot, overlay):
    from aperture_trial import read, write
    from leo.analysis.localization_v3 import family_cavity, feasible
    from leo.analysis.localization_v4.native_bound import NativeBound
    from leo.analysis.research import polynomial_satellite_diagnostics, retained_track_likelihood

    output.mkdir()
    library = overlay.build(output / "library")
    archive = exact.pinned(exact.BASELINE, exact.PINS["scored"])["runs"]["stock"]
    expected = exact.pinned(exact.STAGE / "stock/joint-research-receipt.json", exact.PINS["stock"])
    exact.validate_released_ports(feasible, family_cavity, retained_track_likelihood, polynomial_satellite_diagnostics)
    seen, gates, audit = Captures(), Counter(), {}
    with (patch.object(boot, "load_runtime", return_value=runtime),
          exact.gate_binding(feasible, family_cavity, retained_track_likelihood, gates),
          guard(family_cavity, feasible, audit, first_arm="fitted_c"), seen.monitor(NativeBound)):
        selected = capture(output, "stock", archive, expected, job=exact.STAGE / "request.json",
                           invoke_job=invoke, cutoff=CUTOFF)
    rows = seen.price(overlay, library)
    if gates["visits"] != 58 or audit["first_arm"] != "fitted_c" or len(audit["rejected_trials"]) != 1:
        raise ValueError("The sampling pass did not use the previous fitted-first route")
    eligible = [r for r in rows if r.get("agreement") and r["wider_counts"]["activated"] == 3
                and r["median_wider_cpu_ns"] < r["median_stock_cpu_ns"]]
    price = sum(r["cpu_ns"] * (1 - r["median_wider_cpu_ns"] / r["median_stock_cpu_ns"]) for r in eligible)
    viable = bool(eligible) and all("agreement" in r and (r["agreement"] or r["wider_counts"]["activated"] == 0)
                                    for r in rows)
    write(output / "capture.json", dict(layouts=rows, estimated_net_cpu_ns=price, viable=viable,
          library_sha256=sha256(library.read_bytes()).hexdigest(), build=read(library.parent / "manifest.json"),
          gates=dict(gates), rescue=audit, driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
          protocol_sha256=sha256((HERE / "wide-private-0402-protocol.md").read_bytes()).hexdigest(),
          selection_clock=selected["selection_clock"], capture_clock=selected["capture_clock"],
          ordered_owners={a: len(v) for a, v in selected["rows"].items()},
          root_sources={name: sha256((SOURCES / name).read_bytes()).hexdigest() for name in (
              "algo08_private_width.py", "algo08_private_width.h")}, waveform_calls=0, figures=0, grid=0))


def replay_worker(output, capture_root, runtime, boot, overlay):
    from aperture_trial import read, write
    from leo.analysis.localization_v4.native_bound import NativeBound
    from tools import algo08_position

    source = read(capture_root / "capture.json")
    library = capture_root / "library/private_width.so"
    if not source["viable"] or sha256(library.read_bytes()).hexdigest() != source["library_sha256"]:
        raise ValueError("The bounded call witnesses did not qualify this library")
    original, selected = NativeBound.__call__, algo08_position.selected_packet

    @wraps(selected)
    def selected_stock(*args, **kwargs):
        with patch.object(NativeBound, "__call__", original):
            return selected(*args, **kwargs)

    with (patch.object(boot, "load_runtime", return_value=runtime),
          patch.object(algo08_position, "selected_packet", selected_stock),
          overlay.expand_unsupported_layout(library) as counts):
        veto.worker(output, first_arm="fitted_c")
        result = counts.copy()
    write(output / "wider.json", dict(counts=result, capture_sha256=sha256(
        (capture_root / "capture.json").read_bytes()).hexdigest(), library_sha256=source["library_sha256"]))


def worker(output):
    import empty_bootstrap as boot
    from dense_geographic_trial import host

    host()
    runtime = boot.load_runtime()
    exact.inputs()
    overlay = load_wider()
    if os.environ[MODE] == "capture":
        capture_worker(output, runtime, boot, overlay)
    else:
        replay_worker(output, Path(os.environ[SAMPLE_ROOT]), runtime, boot, overlay)


def evaluate(root, destination):
    from aperture_trial import read, write
    from leo.contracts.digests import canonical_digest

    baseline = exact.pinned(FITTED_ONLY, FITTED_SHA)
    stock = exact.pinned(exact.BASELINE, exact.PINS["scored"])["runs"]["stock"]
    output = root / "exact"
    clock = read(root / "exit.json")["timing"]
    if clock["exit_code"]:
        raise ValueError("The sole wider publication did not reach process exit")
    candidate = exact.inspect(output, "wider", read(output / exact.SETTINGS["audit_name"])["receipt"],
                              clock, exact.inputs(), **exact.SETTINGS)
    failure = None
    try:
        exact.compare(candidate, stock)
    except ValueError as error:
        failure = str(error)
    current, old = candidate["terminal"]["arms"], stock["terminal"]["arms"]
    write(destination, dict(old_exit=baseline["combined_exit"], old_solve=baseline["combined_solve"],
          new_exit=clock, new_solve=candidate["worker"]["solve"], terminal=candidate["terminal"],
          equality_error=failure, role_equality=candidate["selected_rows"] == stock["selected_rows"],
          figures={k: dict(size=tuple(v["size"]) == tuple(stock["figures"][k]["size"]),
                           png=v["sha256"] == stock["figures"][k]["sha256"],
                           rgba=v["rgba_sha256"] == stock["figures"][k]["rgba_sha256"]) for k, v in candidate["figures"].items()},
          sidecars=candidate["sidecars"], sidecars_equal=candidate["sidecars"] == stock["sidecars"],
          owners={k: dict(rows=len(v), sha256=canonical_digest(v)) for k, v in candidate["selected_rows"].items()},
          arm_drift={a: dict(latlon_deg=[x-y for x, y in zip(v["latlon"], old[a]["latlon"], strict=True)],
                             rf_hz=v["rf_rms_hz"] - old[a]["rf_rms_hz"]) for a, v in current.items()},
          exact_gates=read(output / "exact-gates.json"), veto=read(output / "terminal-veto.json"),
          wider=read(output / "wider.json"), fitted_only_receipt_sha256=FITTED_SHA, waveform_calls=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    for mode in ("capture", "replay", "worker", "evaluate"):
        command = commands.add_parser(mode)
        command.add_argument("root", type=Path)
        if mode == "replay":
            command.add_argument("capture", type=Path)
        if mode == "evaluate":
            command.add_argument("destination", type=Path)
    options = parser.parse_args()
    if options.mode == "worker":
        worker(options.root)
    elif options.mode == "evaluate":
        evaluate(options.root, options.destination)
    else:
        source = str(options.capture) if options.mode == "replay" else ""
        with patch.dict(os.environ, {MODE: options.mode, SAMPLE_ROOT: source}):
            exact.launch(options.root, driver=__file__)
