"""Finish the frozen no-repair v5 position decision from the compact cavity state."""

import sys
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.variants import orbit_projector, v5_core, v5_lean

BOUNDARY = "Stored native detector input to both compact v5 final positions"


def finish(archive, identities, prepared, scan, cavity, stage_s):
    from leo.analysis.localization_v3.additional_recovery import recover_additional
    from leo.analysis.localization_v3.reassociation_context import adopt_additional, rank_families
    from leo.analysis.localization_v3.reassociation_history import select_history
    from leo.analysis.localization_v3.recovery_inventory import (
        baseline_pair,
        publication_support,
        recovery_context,
    )
    from leo.analysis.localization_v3.residual_preflight import preflight, rank_targets
    from leo.analysis.localization_v3.residual_screen import screen_candidates
    from leo.analysis.localization_v3.selected_incumbent import reconstruct_incumbent

    from leo.application import localization_v3 as policy

    if not identities or len(set(identities)) != len(identities):
        raise ValueError("Explicit unique scan identities required")
    native = prepared["tracks"]
    observations = native["observations"]
    metadata = prepared["sky"]["metadata"]
    cutoff = metadata["cutoff_utc_ns"]

    def stage(name, operation, *args, **kwargs):
        start = perf_counter()
        result = operation(*args, **kwargs)
        stage_s[name] = perf_counter() - start
        return result

    catalogue = stage("recovery_catalogue", policy.prepare_additional_catalogue, archive, cutoff)
    if catalogue["cutoff_utc_ns"] != cutoff:
        raise ValueError("Recovery catalogue and native scan cutoffs differ")

    def incumbent_support():
        context = recovery_context(scan, cavity)
        arms, all_owners = baseline_pair(context)
        support = publication_support(cavity["policy_arms"], all_owners)
        return context, arms, {arm: row["owners"] for arm, row in support.items()}

    context, arms, owners = stage("cavity_replay", incumbent_support)

    # The bound baseline runs no predictive attempts. Numerical replay and gap recovery
    # receive that empty schedule, so the selected likelihood is still the cavity winner.
    def fresh():
        return reconstruct_incumbent(context, arms, owners)

    def residual_evidence():
        residual = fresh()
        ranked = rank_targets(native["tracks"], observations, owners, sorted(identities))
        return residual, preflight(residual, ranked["targets"], metadata)

    residual, packet = stage("residual", residual_evidence)
    screen = stage("residual_screen", screen_candidates, packet, catalogue, scan.search_region)
    if screen["case"] != packet["case"] or [t["source"] for t in screen["targets"]] != [
        t["source"] for t in packet["targets"]
    ]:
        raise ValueError("Residual screen does not bind to the prepared native targets")
    addition = stage(
        "addition",
        recover_additional,
        fresh,
        owners,
        screen,
        catalogue,
        observations,
        family_count=len(residual["families"]),
        clock=perf_counter,
    )
    incumbent = stage(
        "incumbent",
        adopt_additional,
        fresh,
        arms,
        owners,
        None,
        addition,
        screen,
        catalogue,
        observations,
    )
    _, targets = stage("ranking", rank_families, incumbent["context"])
    admission = stage(
        "admission",
        policy.screen_reassociation_candidates,
        dict(incumbent, status="reassociation_prepared"),
        dict(status="reassociation_targets_ranked", targets=targets),
        catalogue,
        metadata,
    )
    history = []

    def collect(request):
        if not history:
            history.append(policy.prepare_reassociation_history(archive, cutoff))
        return select_history(history[0], request)

    retained = []
    final = stage(
        "final",
        policy.fit_reassociation,
        dict(incumbent, status="reassociation_prepared"),
        admission,
        catalogue,
        metadata,
        collect,
        on_selected=lambda likelihood, pair: retained.append((likelihood, pair)),
    )
    if not final["recovery_complete"]:
        raise ValueError(f"Reassociation incomplete: {final['recovery']['execution_status']}")
    recovery = final["recovery"]
    chosen = recovery["selected"]
    if len(retained) != int(chosen is not None):
        raise ValueError("Reassociation decision and selected state differ")
    if chosen is None:
        selected_context, selected_arms, selected_owners = (
            incumbent[k] for k in ("context", "arms", "owners")
        )
    else:
        selected_context, selected_arms = retained[0]
        selected_owners = {arm: r["proposed_owners"] for arm, r in selected_arms.items()}
    for arm, (_, x) in selected_context["problems"].items():
        if not np.array_equal(x, recovery["final"][arm]["x"]):
            raise ValueError("Selected numerical position differs from final decision")
        if len(selected_owners[arm]) != recovery["final"][arm]["associated"]:
            raise ValueError("Selected native ownership differs from final decision")

    # Use the same output validation and conditional Doppler metric as the full control.
    result = v5_lean._position_result(
        dict(
            native=native,
            arms=selected_arms,
            context=selected_context,
            owners=selected_owners,
            stage_timings=[],
        )
    )
    result.pop("stage_timings")
    result["boundary"] = BOUNDARY
    result["metrics"].update(
        residual_targets=len(packet["targets"]),
        addition_status=addition["decisions"]["72h_30s"]["status"],
        reassociation_targets=targets,
        reassociation_admitted=len(admission["admission"]["admitted"]),
        reassociation_selected=chosen,
    )
    return result


def run(case, work_dir):
    from tools.pipeline_eval.__main__ import local_output

    work_dir = local_output(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    library = work_dir / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, work_dir, Path(__file__), worker_args=(str(library),))


def worker(request, result, library):
    from leo.analysis.localization_v3 import family_cavity

    from leo.operations.tle_archive import TleArchiveReader

    core_infer = v5_core.infer
    make_nominations = family_cavity.nominate_families
    fit_cavity = family_cavity.cavity_policy
    cavity = {}

    def nominate(signed):
        nominations = make_nominations(signed)
        cavity.update(signed=signed, nominations=nominations)
        return nominations

    def fit(signed, nominations):
        result = fit_cavity(signed, nominations)
        cavity["fit"] = result
        return result

    def infer(prepared, region, bound, stage_s):
        core = core_infer(prepared, region, bound, stage_s)
        if core["status"] != "ok":
            return core
        signed = cavity["signed"]
        if "fit" not in cavity:
            # The cavity-only worker skips replay when there is no proposal. The
            # finish needs the checked incumbent state even in that case.
            start = perf_counter()
            fit(signed, cavity["nominations"])
            stage_s["cavity"] += perf_counter() - start
        selected = cavity["fit"]
        if selected["status"] != "complete":
            raise ValueError(f"Cavity fit failed: {selected.get('error')}")
        # core.worker has already authenticated the bound request and its native inputs.
        job = v5_lean._read(request)["job"]
        archive = TleArchiveReader(Path(job["tle_root"]))
        result = finish(
            archive, job["scan_identities"], prepared, signed["scan"], selected, stage_s
        )
        result["metrics"] = dict(core["metrics"], **result["metrics"])
        return result

    # The original cavity controls are source bound. Capture their in-process
    # stage values in this dedicated worker without changing that source.
    with ExitStack() as stack:
        stack.enter_context(patch.object(family_cavity, "nominate_families", nominate))
        stack.enter_context(patch.object(family_cavity, "cavity_policy", fit))
        stack.enter_context(patch.object(v5_core, "infer", infer))
        orbit_projector.worker(request, result, library)


if __name__ == "__main__":
    worker(*sys.argv[1:])
