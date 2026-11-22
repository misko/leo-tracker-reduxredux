"""Time alternate native Gamma update schedules through selected evidence."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from time import process_time
import traceback
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v3.recovery_inventory import recovery_context
from leo.analysis.localization_v4.backend import read_manifest, validate_manifest
from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from solver_trial import measure
from tools import algo08_position
from tools.pipeline_eval.variants import algo08_robust_warm


def inspect_fixed_inputs(raw, archive, assets, offer, library):
    """Compare identical post-selection bound inputs in both calibration arms."""
    report = {}
    original = algo08_position.selected_packet
    port = SimpleNamespace(NativeBound=algo08_position.NativeBound)
    manifest = validate_manifest(read_manifest(assets / "native/manifest.json"), check_provider=True)

    def evidence(prepared, signed, fit):
        packet = original(prepared, signed, fit)
        if fit is None:
            fit = dict(status="complete", accepted=False, baseline_node=signed["node"],
                       baseline_entries=signed["entries"], baseline_means=signed["means"],
                       original_mask=signed["keep"], powers=signed["powers"], model=signed["model"],
                       policy_arms=signed["arms"])
        context = recovery_context(signed["scan"], fit)

        for arm, (problem, endpoint) in context["problems"].items():
            original_bound = problem.scan.bound
            half = problem.scan.search_region.half_width_km
            points = dict(endpoint=endpoint, center=np.zeros(2), corner=np.full(2, half))
            report[arm] = {}
            changes = []

            def compare(*args, **kwargs):
                control = original_bound(*args, **kwargs)
                candidate = accelerated(*args, **kwargs)
                fields = ("conditional_residual_hz", "noise_precision", "prior_group_precision",
                          "coefficient", "noise_gamma_cost", "prior_gamma_cost", "logvolume",
                          "negative_twice_elbo")
                changes.append(dict(
                    observations=len(args[0]),
                    control_iterations=control["precision_iterations"],
                    accelerated_iterations=candidate["precision_iterations"],
                    control_log_precision_change=control["final_log_precision_change"],
                    accelerated_log_precision_change=candidate["final_log_precision_change"],
                    maximum_absolute_change={f: float(np.max(
                        np.abs(control[f] - candidate[f]), initial=0)) for f in fields},
                ))
                return control

            with patch.object(problem.scan, "bound", compare):
                for role, xy in points.items():
                    changes.clear()
                    getattr(problem, "curved_calculate", problem.calculate)(xy)
                    report[arm][role] = changes.copy()
        return packet

    with (
        algo08_robust_warm.binding(port, library, accelerate=True),
        patch.object(algo08_position, "selected_packet", evidence),
    ):
        accelerated = port.NativeBound(manifest["binary"])
        result = measure("combined", raw, archive, assets, offer)
    return dict(decision=result["decision"], fixed_inputs=report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    parser.add_argument("--library", type=Path)
    parser.add_argument("--accelerate", action="store_true")
    parser.add_argument("--audit-fixed", action="store_true")
    args = parser.parse_args()
    if args.accelerate and args.library is None:
        parser.error("--accelerate requires an accelerated --library")
    if args.audit_fixed and not args.accelerate:
        parser.error("--audit-fixed requires --accelerate")
    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Native detections differ from their declared digest")
    offer = Algo08Region.parse(json.loads(args.region.read_bytes()))
    if args.audit_fixed:
        report = inspect_fixed_inputs(json.loads(raw), TleArchiveReader(args.archive), args.assets,
                                      offer, args.library)
        print(json.dumps(dict(report, native_sha256=args.native_sha256, region=offer.document()),
                         allow_nan=False))
        return
    with algo08_robust_warm.binding(algo08_position, args.library, accelerate=args.accelerate) as metrics:
        started = process_time()
        try:
            results = measure("combined", json.loads(raw), TleArchiveReader(args.archive),
                              args.assets, offer)
        except ValueError as error:
            results = dict(cpu_s=process_time() - started, failure=str(error),
                           frame=traceback.extract_tb(error.__traceback__)[-1].name)
    mode = "accelerate" if args.accelerate else "warm" if args.library is not None else "control"
    print(json.dumps(dict(results, mode=mode, native_metrics=metrics,
                          native_sha256=args.native_sha256, region=offer.document()), allow_nan=False))


if __name__ == "__main__":
    main()
