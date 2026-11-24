"""Choose named or lean inference from the authenticated earlier orbit catalogue."""

from contextlib import ExitStack, contextmanager
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace
from unittest.mock import patch


def checked_census(prepared, modes, cutoff):
    import numpy as np

    from early_causal_history import census

    if prepared.get("status") != "inputs_prepared":
        raise ValueError("The original numerical inputs are unavailable")

    def propagated(catalogue, origin, samples):
        position, velocity, usable = modes.ecef_states(catalogue, origin, samples)
        rows = len(catalogue.satellite_numbers)
        if (usable.shape != (rows,) or usable.dtype != bool
                or position.shape != velocity.shape or position.shape != (rows, len(samples), 3)):
            raise ValueError("The earlier orbit check returned an unexpected sample layout")
        usable = usable & np.isfinite(position).all(axis=(1, 2)) & np.isfinite(velocity).all(axis=(1, 2))
        return position, velocity, usable

    result = census(prepared["sky"], SimpleNamespace(parse_element_sets=modes.parse_element_sets, ecef_states=propagated))
    if result["cutoff_utc_ns"] != cutoff or any(not row["earlier_rows"] for row in result["prior"].values()):
        raise ValueError("Both genuine earlier catalogues must be available at the original cutoff")
    return result


def select(probe, prepared):
    started = process_time_ns(), perf_counter_ns()
    try:
        result = probe(prepared)
        if set(result["prior"]) != {"previous", "genuine_previous"}:
            raise ValueError("The earlier orbit census is incomplete")
        risky = any(row["unusable"] for row in result["prior"].values())
        decision = dict(route="named" if risky else "lean", reason="unusable_earlier_orbit" if risky else "healthy_samples",
                        census=result)
    except Exception as error:
        # The probe cannot authorize lean unless it independently verifies the entire input.
        decision = dict(route="named", reason="probe_unavailable", error=f"{type(error).__name__}: {error}")
    return decision | dict(cpu_ns=process_time_ns()-started[0], elapsed_ns=perf_counter_ns()-started[1])


def choose_once(named, lean, probe, audit):
    def run(prepared, *args, **kwargs):
        if "choice" not in audit:
            audit["choice"] = select(probe, prepared)
        audit["inference_calls"] = audit.get("inference_calls", 0) + 1
        operation = lean if audit["choice"]["route"] == "lean" else named
        return operation(prepared, *args, **kwargs)

    return run


@contextmanager
def binding(reader, cutoff, audit, original_rank):
    from leo.analysis.localization_v3 import orbit_modes
    from tools.pipeline_eval.variants import v5_core
    from joint_publication import full_catalogue_route
    from isolated_salvage import binding as isolated_families
    from named_survivor_fit import binding as named_finish
    from prepared_exterior import handoff

    original, exact_rank = v5_core.infer, v5_core.ranked_initial_nodes
    audit.update(lean_attempts=[], lean_final_fit={})

    def fallback(*args, **kwargs):
        with patch.object(v5_core, "ranked_initial_nodes", exact_rank):
            return original(*args, **kwargs)

    def lean(*args, **kwargs):
        with ExitStack() as stack:
            # Lean already prepares shared rank inputs inside its own ranked search.
            stack.enter_context(patch.object(v5_core, "ranked_initial_nodes", original_rank))
            stack.enter_context(isolated_families())
            stack.enter_context(named_finish(audit["lean_final_fit"]))
            cumulative = full_catalogue_route(fallback, reader, audit["lean_attempts"], optimized=True)
            return cumulative(*args, **kwargs)

    run = choose_once(original, lean, lambda ready: checked_census(ready, orbit_modes, cutoff), audit)
    with handoff(reader) as (_, counts, _), patch.object(v5_core, "infer", run):
        yield
    audit["exterior_handoff"] = dict(counts)
