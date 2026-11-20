"""Validate the retained curved-only and linear compact cavity incumbents."""

import sys
from pathlib import Path
from unittest.mock import patch

from tools.pipeline_eval.variants import orbit_projector, v5_lean, v5_optional_cavity

METHOD = v5_optional_cavity.METHOD


def curved_phase_receipt(context):
    """Adapt the original curved fit's phase receipt to the shared paired gate."""
    arms = context["arms"]
    if arms is not context["signed"]["policy_arms"]:
        return context
    if not context["signed"]["accepted"] and not context["entries"]:
        arms = {
            arm: (
                fit
                if "final_phase_change_s" in fit
                else dict(fit, final_phase_change_s=fit["history"][-1]["phase_change_s"])
            )
            for arm, fit in arms.items()
        }
        context = dict(context, arms=arms, signed=dict(context["signed"], policy_arms=arms))
    return context


def worker(request, result, library):
    baseline_gate = v5_optional_cavity.incumbent_publishable

    def validate(valid, context):
        # Keep the pinned selector and alter only the gate input's source schema.
        return baseline_gate(valid, curved_phase_receipt(context))

    with patch.object(v5_optional_cavity, "incumbent_publishable", validate):
        v5_optional_cavity.worker(request, result, library)


def run(case, work_dir):
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    library = work / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, work, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
