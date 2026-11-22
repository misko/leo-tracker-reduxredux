"""Count repeated complete likelihood inputs after the frozen endpoint/recovery caches."""

import argparse
import json
import os
import runpy
import sys
import weakref
from collections import Counter, OrderedDict, defaultdict
from contextlib import ExitStack, suppress
from hashlib import sha256
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np

DEFAULTS = dict(prior_groups=None, powers=1.0, noise_nu=4.0, prior_nu=4.0, iterations=256)
NORMALIZED = (
    "y", "u", "s", "g", "selected", "prior", "dimensions", "counts", "power", "alpha", "pa",
    "alpha0", "beta0", "pa0", "pb0", "v0", "iterations",
)
STAGES = dict(
    ranked_initial_nodes="initial-ranking", screen_nodes="initial-fit",
    conservative_recovery="conservative", history_policy="family-history",
    signed_context="signed", nominate_families="cavity", cavity_policy="cavity",
    selected_packet="selected-evidence",
)
MIB = 2**20


def value_key(value):
    if value is None:
        return None, 0
    array = np.asarray(value)
    if array.dtype.hasobject:
        raise ValueError("Object values are outside the numeric likelihood boundary")
    contiguous = np.ascontiguousarray(array)
    data = memoryview(contiguous).cast("B") if contiguous.size else b""
    return (array.dtype.str, array.shape, array.strides, sha256(data).digest()), array.nbytes


def full_key(values, memo=None):
    keys, size = [], 0
    for value in values:
        # Keep the object alive while its numeric key may be reused by _VALIDATE.
        saved = memo.get(id(value)) if memo is not None else None
        descriptor, nbytes = saved[1:] if saved and saved[0] is value else value_key(value)
        if memo is not None and isinstance(value, np.ndarray):
            memo[id(value)] = value, descriptor, nbytes
        keys.append(descriptor)
        size += nbytes
    return tuple(keys), size


def hint(raw, features, arrays_and_options):
    n, p = features.shape
    rows = np.array([0, n // 2, n - 1])
    cols = np.array([0, p // 2, p - 1]) if p else np.empty(0, int)
    return (features.shape, raw[rows].tobytes(), features[np.ix_(rows, cols)].tobytes(),
            full_key(arrays_and_options)[0])


def stack_context(models):
    frame = sys._getframe(2)
    caller = os.path.basename(frame.f_code.co_filename)
    model = frame.f_locals.get("self", frame.f_locals.get("p"))
    token = None
    if model is not None:
        with suppress(TypeError):
            token = models.token(model)
    while frame is not None:
        if frame.f_code.co_name in STAGES:
            return caller, STAGES[frame.f_code.co_name], token
        frame = frame.f_back
    return caller, "other", token


class ModelIdentities(weakref.WeakKeyDictionary):
    # A WeakKeyDictionary can lose old models, so assign monotonic tokens.
    def __init__(self):
        super().__init__()
        self.next_id = 0

    def token(self, instance):
        try:
            return self[instance]
        except KeyError:
            key = self.next_id
            self[instance] = key
            self.next_id += 1
            return key


def simulate(rows, size_limit):
    recent = OrderedDict()
    used = peak = 0
    cost = Counter()
    for row in rows:
        if row["mode"] != "ordinary":
            continue
        key, size = row["raw_key"], row["witness_bytes"]
        if key in recent:
            recent.move_to_end(key)
            cost["hits"] += 1
            cost["gross_avoided_cpu_ns"] += row["cpu_ns"]
            continue
        if size > size_limit:
            continue
        while used + size > size_limit:
            _, expired = recent.popitem(last=False)
            used -= expired
        recent[key] = size
        used += size
        peak = max(peak, used)
        cost["inserted_witness_bytes"] += size
    return dict(peak_witness_bytes=peak, gross_avoided_cpu_ns=cost["gross_avoided_cpu_ns"],
                hits=cost["hits"], inserted_witness_bytes=cost["inserted_witness_bytes"])


def summarize(rows):
    tally = defaultdict(Counter)
    transitions = defaultdict(Counter)
    exact = {key: {} for key in ("raw_key", "normalized_key")}
    hints = defaultdict(set)
    for row in rows:
        count = tally[row["mode"]]
        count["calls"] += 1
        for key in ("cpu_ns", "raw_fingerprint_ns", "normalized_fingerprint_ns", "hint_ns"):
            count[key] += row[key]
        if row["hint"] in hints:
            count["prefilter_candidate_calls"] += 1
        hints[row["hint"]].add(row["raw_key"])
        for key, registry in exact.items():
            old = registry.get(row[key])
            if old is not None:
                count[f"{key}_repeats"] += 1
                count[f"{key}_repeat_cpu_ns"] += row["cpu_ns"]
                count[f"{key}_result_mismatches"] += old["result_key"] != row["result_key"]
                if key == "raw_key":
                    cross = transitions[f"{old['stage']} → {row['stage']}"]
                    cross["repeats"] += 1
                    cross["cpu_ns"] += row["cpu_ns"]
                    models = old["model"], row["model"]
                    cross["different_model"] += None not in models and models[0] != models[1]
            registry[row[key]] = row
    return dict(boundaries=dict(tally), repeats_by_stage=dict(transitions),
                ordinary_lru={str(size): simulate(rows, size * MIB) for size in (8, 32, 64, 128)},
                max_candidate_keys_per_hint=max(map(len, hints.values()), default=0))


def worker(native, spec, archive, offer, output):
    from tools.pipeline_eval.variants.experimental import lean_startup

    install = lean_startup.install
    rows = []
    active = None
    models = ModelIdentities()

    with ExitStack() as stack:
        def install_then_audit():
            install()
            from leo.analysis.localization_v4 import native_bound
            from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff

            bound, validate = native_bound.NativeBound.__call__, native_bound._VALIDATE
            capture, original_grid = handoff.Capture.run, handoff.grid_handoff
            def grid():
                return False

            def grid_handoff(port, library, in_grid):
                nonlocal grid
                grid = in_grid
                return original_grid(port, library, in_grid)

            def export(owner, native_owner, operation, args):
                status = capture(owner, native_owner, operation, args)
                start = process_time_ns()
                state = owner.width, status, owner.exported.value
                factor = full_key((owner.lower, owner.order))[0] if owner.exported.value else None
                if active is None or active["export"] is not None:
                    raise ValueError("Unexpected posterior-export context")
                active["export"] = state
                active["factor"] = factor
                active["factor_ns"] = process_time_ns() - start
                return status

            def validated(*args, **options):
                data = validate(*args, **options)
                start = process_time_ns()
                active["normalized"] = full_key((data[k] for k in NORMALIZED), active["memo"])[0]
                active["normalized_ns"] = process_time_ns() - start
                return data

            def observed(owner, raw, features, sigma, groups, **options):
                nonlocal active
                if active is not None or options.keys() - DEFAULTS.keys():
                    raise ValueError("Unexpected likelihood options or nested native call")
                arguments = [raw, features, sigma, groups, *(DEFAULTS | options).values()]
                context = (owner.manifest["binary_sha256"], owner.provider_info["sha256"],
                           owner.min_rcond.hex(), grid(), type(arguments[-1]).__name__)
                start = process_time_ns()
                prefilter = hint(raw, features, arguments[2:])
                hint_ns = process_time_ns() - start
                active = dict(memo={}, export=None, factor=None, normalized_ns=0, factor_ns=0)
                start = process_time_ns()
                fingerprint, size = full_key(arguments, active["memo"])
                raw_ns = process_time_ns() - start
                caller, stage, model = stack_context(models)
                start = process_time_ns()
                try:
                    result = bound(owner, raw, features, sigma, groups, **options)
                finally:
                    observed, active = active, None
                overhead = observed["normalized_ns"] + observed["factor_ns"]
                elapsed = process_time_ns() - start - overhead
                signature, output_bytes = full_key(result.values())
                mode = "ordinary" if not context[3] else (
                    "grid-export" if observed["export"] is not None else "grid-without-export"
                )
                backend = context + (observed["export"],)
                rows.append(dict(
                    mode=mode, raw_key=backend + fingerprint,
                    normalized_key=backend + observed["normalized"],
                    result_key=(tuple(result), signature, observed["factor"]),
                    hint=context + prefilter, witness_bytes=size+output_bytes,
                    cpu_ns=elapsed, raw_fingerprint_ns=raw_ns,
                    normalized_fingerprint_ns=observed["normalized_ns"], hint_ns=hint_ns,
                    caller=caller, stage=stage, model=model,
                ))
                return result

            stack.enter_context(patch.object(native_bound, "_VALIDATE", validated))
            stack.enter_context(patch.object(native_bound.NativeBound, "__call__", observed))
            stack.enter_context(patch.object(handoff.Capture, "run", export))
            stack.enter_context(patch.object(handoff, "grid_handoff", grid_handoff))

        stack.enter_context(patch.object(lean_startup, "install", install_then_audit))
        helper = Path(__file__).with_name("residual_attribution_trial.py")
        run = runpy.run_path(str(helper))["worker"]
        run(native, spec, archive, offer, output / "terminal.json", include_evidence=True)
    with (output / "audit.json").open("x") as stream:
        json.dump(summarize(rows), stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("native", "spec", "archive", "offer", "output"):
        parser.add_argument(name, type=Path)
    options = parser.parse_args()
    options.output.mkdir(parents=True, exist_ok=False)
    worker(**vars(options))
