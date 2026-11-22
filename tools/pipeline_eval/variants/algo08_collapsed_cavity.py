"""Opt in to the deployed complete-family cavity after collapsed signed refinement."""

from contextlib import contextmanager
from functools import wraps
from time import process_time
from unittest.mock import patch

import numpy as np


def arm_readout(arms):
    return {arm: dict(latlon=list(row["endpoint_latlon"]), rf_rms_hz=float(row["RMS_hz"]))
            for arm, row in arms.items()}


def validate_context(signed, incumbent):
    # The signed stage retains the same scan and may copy the empty-predictive
    # arm records to add empty linear gates. Its numerical incumbent must agree.
    if (any(signed[key] is not incumbent[key] for key in ("scan", "node", "model"))
            or any(not np.array_equal(signed[key], incumbent[key])
                   for key in ("keep", "powers", "means"))
            or (signed["entries"] is not incumbent["entries"]
                and (signed["entries"] or incumbent["entries"]))):
        raise ValueError("Complete-family cavity lacks the selected signed incumbent")
    for arm, selected in incumbent["arms"].items():
        saved = signed["arms"][arm]
        if any(saved[key] is not selected[key] for key in ("phase_reference", "state")):
            raise ValueError("Complete-family cavity has different signed arm state")


def with_cavity(infer):
    from leo.analysis.localization_v3 import family_cavity, signed_context

    @wraps(infer)
    def run(prepared, region, bound, stages, *, selected_evidence=None):
        context, cavity, diagnostics = None, None, None
        original_signed = signed_context.signed_context

        @wraps(original_signed)
        def retain(*args, **kwargs):
            nonlocal context
            if context is not None:
                raise ValueError("Expected one collapsed signed context")
            context = original_signed(*args, **kwargs)
            return context

        def evidence(ready, incumbent, fit):
            nonlocal cavity, diagnostics
            if context is None or fit is not None:
                raise ValueError("Expected the collapsed signed incumbent before cavity")
            validate_context(context, incumbent)
            start = process_time()
            nominations = family_cavity.nominate_families(context)
            nomination_cpu = process_time() - start
            if nominations["status"] != "complete":
                raise ValueError(f"cavity nomination failed: {nominations.get('error')}")
            offered = [dict(original=row["original_norad"], alternate=row["best"]["norad"],
                            gain=row["predictive_gain"]) for row in nominations["families"]
                       if row["best"] is not None and row["predictive_gain"] > 0]
            diagnostics = dict(nomination_cpu_s=nomination_cpu, fit_cpu_s=0.0,
                               catalogue=len(context["scan"].norads),
                               families=len(nominations["families"]), offers=offered,
                               incumbent=arm_readout(incumbent["arms"]), accepted=False)
            if offered:
                start = process_time()
                cavity = family_cavity.cavity_policy(context, nominations)
                diagnostics["fit_cpu_s"] = process_time() - start
                if cavity["status"] != "complete":
                    raise ValueError(f"cavity fit failed: {cavity.get('error')}")
                diagnostics.update(
                    accepted=cavity["accepted"],
                    trials=[dict(replacements=t["replacements"], paired_valid=t["paired_valid"])
                            for t in cavity["trials"]],
                    selected=cavity["selected"]["replacements"] if cavity["accepted"] else [],
                )
            if selected_evidence is not None:
                selected_evidence(ready, context, cavity)

        with patch.object(signed_context, "signed_context", retain):
            result = infer(prepared, region, bound, stages, selected_evidence=evidence)
        if diagnostics is not None:
            result["metrics"]["complete_family_cavity"] = diagnostics
        if cavity is not None and cavity["accepted"]:
            result["arms"] = arm_readout(cavity["policy_arms"])
        return result

    return run


@contextmanager
def collapsed_cavity():
    """Wrap the repair binding before the exterior guard is installed."""
    from tools.pipeline_eval.variants import algo08_collapsed_repair, v5_core

    original_binding = algo08_collapsed_repair.binding

    @contextmanager
    def bind(*args, **kwargs):
        with (original_binding(*args, **kwargs),
              patch.object(v5_core, "infer", with_cavity(v5_core.infer))):
            yield

    with patch.object(algo08_collapsed_repair, "binding", bind):
        yield
