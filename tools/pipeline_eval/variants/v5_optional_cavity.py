"""Keep family-exclusion nonconvergence local to the optional cavity proposal."""

import hashlib
import json
import math
import sys
from pathlib import Path
from unittest.mock import patch

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.variants import orbit_projector, v5_core, v5_lean, v5_secant_fit

METHOD = "v5_optional_cavity"
BOUNDARY = "Compact secant v5 with family-local cavity nonconvergence"
FAMILY_SHA256 = "7a20ac84d4c245df95481d10425def01642cbf4d3f45f1f32b9188a78007b3ae"
NONCONVERGENCE = "family-excluded calibration phase did not converge"


class UnqualifiedPair(Exception):
    """No independently selected replacement and no publishable incumbent remained."""


def try_family(build, context, target, rejected):
    try:
        return build(context, target)
    except ValueError as error:
        leaf = error.__traceback__
        while leaf.tb_next is not None:
            leaf = leaf.tb_next
        if (
            type(error) is not ValueError
            or error.args != (NONCONVERGENCE,)
            or (leaf.tb_frame.f_code is not build.__code__)
        ):
            raise
        rejected.append(dict(norad=int(context["scan"].norads[target]), reason=NONCONVERGENCE))
        # A family without held evidence cannot nominate a replacement.
        return {"values": ()}


def incumbent_publishable(valid, context):
    arms = context["arms"]
    if (
        arms is not context["signed"]["policy_arms"]
        or set(arms) != set(v5_lean.ARMS)
        or not valid(arms, half_width_km=context["scan"].search_region.half_width_km)
    ):
        return False
    return all(
        len(fit["endpoint_latlon"]) == 2
        and all(math.isfinite(x) for x in fit["endpoint_latlon"])
        and math.isfinite(fit["final_phase_change_s"])
        and math.isfinite(fit["RMS_hz"])
        for fit in arms.values()
    )


def worker(request, result, library):
    from leo.analysis.localization_v3 import family_cavity

    if hashlib.sha256(Path(family_cavity.__file__).read_bytes()).hexdigest() != FAMILY_SHA256:
        raise ValueError("unrecognized family-cavity proposal contract")
    original_build = family_cavity.family_data
    original_nominate = family_cavity.nominate_families
    original_restore = family_cavity.cavity_policy
    original_infer = v5_core.infer
    rejected, attempted = [], []
    evidence = {"rejected": rejected, "attempted_norads": attempted}

    def build(context, target):
        attempted.append(int(context["scan"].norads[target]))
        return try_family(original_build, context, target, rejected)

    def require_incumbent(context):
        valid = incumbent_publishable(family_cavity.valid, context)
        evidence["incumbent_gate_passed"] = valid
        if not valid:
            raise UnqualifiedPair("family-local cavity rejection left no qualified paired position")

    def nominate(context):
        outcome = original_nominate(context)
        if rejected and outcome["status"] == "complete":
            evidence["remaining_families"] = len(outcome["families"])
            if not any(
                f["best"] is not None and f["predictive_gain"] > 0 for f in outcome["families"]
            ):
                require_incumbent(context)
                evidence["selected"] = "incumbent"
        return outcome

    def restore(context, nominations):
        outcome = original_restore(context, nominations)
        if outcome["status"] == "complete":
            evidence["selected"] = "replacement" if outcome["accepted"] else "incumbent"
            evidence["trials"] = len(outcome["trials"])
            if rejected and not outcome["accepted"]:
                require_incumbent(context)
        return outcome

    def infer(prepared, region, bound, stages, **options):
        try:
            return original_infer(prepared, region, bound, stages, **options)
        except UnqualifiedPair as error:
            return dict(
                status="withheld",
                reason=str(error),
                boundary=BOUNDARY,
                metrics={"stage_s": stages},
                arms={a: {"latlon": None} for a in v5_lean.ARMS},
            )

    with (
        patch.object(family_cavity, "family_data", build),
        patch.object(family_cavity, "nominate_families", nominate),
        patch.object(family_cavity, "cavity_policy", restore),
        patch.object(v5_core, "infer", infer),
    ):
        v5_secant_fit.worker(request, result, library, "secant")
    report = json.loads(Path(result).read_bytes())
    report["boundary"] = BOUNDARY
    report["metrics"]["optional_cavity"] = evidence
    save_json(Path(result), report)


def run(case, work_dir):
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    library = work / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, work, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
