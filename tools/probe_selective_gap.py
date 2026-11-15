"""Replay a public result and screen its direct-gap target without optimization."""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

from census_algo07v5_initial_controls import fingerprint
from probe_algo07v5_annotation_rounds import load_context, request_inputs

from leo.analysis.localization_v3.gap_controller import direct_timing_targets
from leo.analysis.localization_v3.gap_prediction import screen_timing_targets
from leo.analysis.localization_v4.backend import ProcessBound, build_native, read_manifest
from leo.application.localization_v3_engine import _json_value
from leo.operations.localization_v3_job import stage_deadline


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--publication", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=90, choices=range(1, 121))
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists() or output.is_relative_to("/mnt/qnap01"):
        parser.error("fresh local output required")
    if len(os.sched_getaffinity(0)) != 1 or os.environ.get("OPENBLAS_NUM_THREADS") != "1":
        parser.error("pin exactly one CPU and one BLAS thread")
    request, job, store = request_inputs(args.request)
    publication = args.publication or Path(job["output_root"])
    if not publication.is_dir():
        parser.error("existing public result directory required")
    output.mkdir(parents=True)
    began = time.perf_counter()
    with stage_deadline(args.timeout):
        saved = store(publication).load(job["identity"]["run_id"])

        class LoadedStore:
            def __init__(self, root):
                pass

            def load(self, run_id):
                if run_id != job["identity"]["run_id"]:
                    raise ValueError("saved run changed")
                return saved

        manifest = read_manifest(build_native(output / "native"))
        for key in ("source_sha256", "wrapper_sha256", "provider", "flags", "original_sha256"):
            if manifest[key] != request["backend_manifest"][key]:
                raise ValueError("replay native source or numerical provider changed")
        backend = ProcessBound(manifest, output / "native-receipts")
        context, evidence, binding = load_context(request, job, LoadedStore, backend)
        observations = saved["evidence"]["preparation"]["tracks"]["observations"]
        inventory, owners = evidence["inventory"], evidence["owners"]
        before = fingerprint((context["scan"].tracks, inventory, observations, owners))
        coefficients = {arm: p.calculate(x)["coefficient"].copy()
                        for arm, (p, x) in context["problems"].items()}
        targets = direct_timing_targets(context, inventory, owners)
        started = time.perf_counter()
        result = screen_timing_targets(context, inventory, observations, owners, targets)
        screen_seconds = time.perf_counter() - started
        if before != fingerprint((context["scan"].tracks, inventory, observations, owners)):
            raise ValueError("screen changed scientific inputs")
        for arm, (p, x) in context["problems"].items():
            if p.scan is not context["scan"] or fingerprint(coefficients[arm]) != fingerprint(
                    p.calculate(x)["coefficient"]):
                raise ValueError("screen changed the original calibrated posterior")
        files = [Path(__file__), args.request,
                 Path(__file__).parents[1] / "src/leo/analysis/localization_v3/gap_prediction.py"]
        result.update(request=str(args.request.resolve()), publication=str(publication.resolve()),
                      execution_backend_manifest=manifest,
                      source_sha256={str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in files}, binding=binding, input_targets=targets,
                      screen_seconds=screen_seconds, elapsed_seconds=time.perf_counter() - began,
                      original_inputs_unchanged=True, optimization_performed=False,
                      original_posterior_unchanged=True,
                      identity_or_inclusion_authorized=False)
        (output / "result.json").write_text(json.dumps(
            result, default=_json_value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps(dict(output=str(output), input_targets=len(targets),
                          retained=len(result["targets"]), screen_seconds=screen_seconds)))


if __name__ == "__main__":
    main()
