"""Recover an authenticated earlier-orbit failure inside the named v3 fit."""

from contextlib import ExitStack, contextmanager
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


ORBIT_MODES_SHA256 = "778104949ad9467b613ffab820a75db013b33fa86ad810ea00b226841fdc8b52"
POSITION_SHA256 = "cd5c728e7f81b675b796d69713ca66e601a54534bdbf1d606dc8ecf16c4c138c"
HISTORY_SHA256 = "e8557627d5ace817a201160161eb1fd3aec53a804b3906a07d14b5419fbee4d8"
ALIGNMENT_ASSERTION = 44
ALIGNMENT_S = (0., 150., 300.)


def checked(module, source, digest):
    path = Path(module.__file__).resolve(strict=True)
    if path != source or sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError(f"The named v3 history experiment requires the pinned source {source}")


def last_frame(error):
    trace = error.__traceback__
    while trace.tb_next is not None:
        trace = trace.tb_next
    return trace


def recovered_catalogue(error, previous, line, scan, labels, modes, subset):
    """Admit only the initial SGP4 health assertion in the pinned previous bank."""
    import numpy as np

    trace = last_frame(error)
    if (type(error) is not AssertionError or error.args or trace.tb_frame.f_code is not previous.__code__
            or trace.tb_lineno != line):
        return None
    scope = trace.tb_frame.f_locals
    if (scope["scan"] is not scan or scope["labels"] is not labels
            or not np.array_equal(scope["sample"], ALIGNMENT_S)):
        return None
    old = modes.parse_element_sets(scan.previous_tle)
    selected = {int(scan.norads[index]) for index in labels}
    candidates = subset(old, [i for i, n in enumerate(old.satellite_numbers) if n in selected])
    sampled = scope["cat"].satellite_numbers
    good = scope["good"]
    if (not candidates.satellites or len(sampled) != len(candidates.satellite_numbers)
            or set(sampled) != set(candidates.satellite_numbers) or good.dtype != bool
            or good.shape != (len(sampled),) or good.all()):
        return None
    observed = {int(n) for n, ok in zip(sampled, good, strict=True) if not ok}
    # Use the same order and propagation as the named retry's isolation step.
    _, _, confirmed = modes.ecef_states(candidates, scan.origin_utc_ns, np.array(ALIGNMENT_S))
    failed = {int(n) for n, ok in zip(candidates.satellite_numbers, confirmed, strict=True) if not ok}
    if failed != observed or not scan.previous_sources or not failed <= {int(n) for n in scan.previous_sources}:
        return None
    usable = subset(old, [i for i, n in enumerate(old.satellite_numbers) if n not in failed])
    event = dict(previous_tle_sha256=scan.previous_tle_sha256, origin_utc_ns=int(scan.origin_utc_ns),
                 alignment_seconds=ALIGNMENT_S, failed_previous_norads=sorted(failed),
                 previous_sources={str(n): scan.previous_sources[str(n)] for n in sorted(failed)},
                 assertion=dict(source=previous.__code__.co_filename, line=line, function=previous.__name__))
    return usable, event


@contextmanager
def recover_previous(modes, retained, subset, events, *, line=ALIGNMENT_ASSERTION):
    previous, parsed = modes.previous_bank, modes.parse_element_sets

    def isolate(scan, labels):
        try:
            return previous(scan, labels)
        except AssertionError as error:
            start = process_time_ns(), perf_counter_ns()
            observed = recovered_catalogue(error, previous, line, scan, labels, modes, subset)
            if observed is None:
                raise
        usable, event = observed

        def verified_catalogue(text):
            if text != scan.previous_tle:
                raise ValueError("Unexpected earlier catalogue during local orbit recovery")
            return usable

        with patch.object(modes, "parse_element_sets", verified_catalogue):
            result = previous(scan, labels)
        events.append(dict(event, cpu_ns=process_time_ns() - start[0], elapsed_ns=perf_counter_ns() - start[1]))
        return result

    with (patch.object(modes, "previous_bank", isolate), patch.object(retained, "previous_bank", isolate)):
        yield


def observe(operation, readings):
    def measure(*args, **kwargs):
        start = process_time_ns(), perf_counter_ns()
        status = "raised"
        try:
            result = operation(*args, **kwargs)
            status = "returned"
            return result
        finally:
            readings.append(dict(status=status, cpu_ns=process_time_ns() - start[0],
                                 elapsed_ns=perf_counter_ns() - start[1]))

    return measure


@contextmanager
def named_solve(enabled, release, payload):
    """Wrap the same named solve in both modes and preserve its published policy."""
    from leo.analysis.localization_v3 import orbit_modes, retained_position
    from tools import algo08_position, algo08_scan
    from tools.pipeline_eval.qualification import compact_history_replay
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard

    orbit_source = release / "src/leo/analysis/localization_v3/orbit_modes.py"
    checked(orbit_modes, orbit_source, ORBIT_MODES_SHA256)
    checked(algo08_position, payload / "tools/algo08_position.py", POSITION_SHA256)
    checked(compact_history_replay, payload / "tools/pipeline_eval/qualification/compact_history_replay.py",
            HISTORY_SHA256)
    original = algo08_scan.solve
    if (original is not algo08_position.solve
            or Path(orbit_modes.previous_bank.__code__.co_filename).resolve() != orbit_source
            or retained_position.previous_bank is not orbit_modes.previous_bank):
        raise ValueError("The named solve or previous-bank aliases differ from the expected binding")
    audit = dict(enabled=enabled, solves=0, prepare=[], infer=[], exterior_proof=[], events=[])

    def solve(*args, **kwargs):
        audit["solves"] += 1
        with ExitStack() as stack:
            for owner, attribute, stage in (
                (algo08_position, "prepare_native_scan", "prepare"),
                (v5_core, "infer", "infer"),
                (regional_bound_guard, "causal_probes", "exterior_proof"),
            ):
                stack.enter_context(patch.object(owner, attribute, observe(getattr(owner, attribute), audit[stage])))
            if enabled:
                stack.enter_context(recover_previous(orbit_modes, retained_position, compact_history_replay.subset,
                                                     audit["events"]))
            result, packet, policy = original(*args, **kwargs)
        audit["original_policy"] = policy
        if policy == "stock" and audit["events"]:
            policy = "history_support"
        audit["published_policy"] = policy
        return result, packet, policy

    with patch.object(algo08_scan, "solve", solve):
        yield audit
