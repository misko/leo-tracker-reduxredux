"""Capture exact native-to-prepared stage evidence and complete v5 decisions."""

import json
import sys
from contextlib import ExitStack
from functools import wraps
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.qualification import early_memory_worker
from tools.pipeline_eval.qualification.early_memory_worker import memory_categories
from tools.pipeline_eval.qualification.working_memory_worker import fingerprint, rss
from tools.pipeline_eval.variants import prep_stream_sky


def worker(request, result, library, mode):
    from leo.application import localization_v3
    from leo.operations import localization_v3_inputs, localization_v3_job

    native = json.loads(Path(request).read_bytes())["job"]["native_input"]
    stages, evidence = {}, {}

    def watched(name, operation, hash_output=None):
        @wraps(operation)
        def timed(*args, **kwargs):
            before, categories = rss(), memory_categories()
            wall, cpu = perf_counter(), process_time()
            value = operation(*args, **kwargs)
            stages[name] = dict(
                before=before,
                after=rss(),
                before_categories=categories,
                after_categories=memory_categories(),
                wall_s=perf_counter() - wall,
                cpu_s=process_time() - cpu,
            )
            if hash_output is not None:
                evidence[name] = hash_output(value)
            return value

        return timed

    def graph(value):
        return fingerprint(
            (value["tracks"], value["observations"], value["metadata"], value["curved_indices"])
        )

    def regional(value):
        return dict(
            order=fingerprint(value["source_indices"]),
            catalogue=fingerprint((value["catalogue"].names, value["catalogue"].satellite_numbers)),
            data=fingerprint(value["bank"]),
            selected=len(value["source_indices"]),
        )

    def original_sky(value):
        return fingerprint({k: v for k, v in value.items() if k != "bank"})

    baseline_prepare = localization_v3.prepare_native_scan

    @wraps(baseline_prepare)
    def prepare(*args, element_parser=None, **kwargs):
        parser = localization_v3.ElementParser() if element_parser is None else element_parser
        value = baseline_prepare(*args, element_parser=parser, **kwargs)
        if hasattr(parser, "statistics"):
            stages["element_cache"] = parser.statistics()
        return value

    original_read = localization_v3_job.read_bound
    measured_read = watched("native_decode", original_read)

    def read(record):
        return (measured_read if record == native else original_read)(record)

    with ExitStack() as stack:
        used = stack.enter_context(prep_stream_sky.prepared_sky()) if mode == "stream" else {}
        stack.enter_context(patch.object(localization_v3_job, "read_bound", read))
        for owner, member, name, signature in (
            (localization_v3, "prepare_native_scan", "native_to_prepared", None),
            (localization_v3, "prepare_tracks", "graph", graph),
            (localization_v3, "prepare_initial_sky", "initial_sky", original_sky),
            (localization_v3_inputs, "regional_bank", "regional_bank", regional),
            (localization_v3, "prepare_phase_history", "phase_history", fingerprint),
            (localization_v3, "forecast", "phase_forecast", fingerprint),
            (localization_v3, "estimate_noise", "noise", fingerprint),
        ):
            actual = prepare if member == "prepare_native_scan" else getattr(owner, member)
            stack.enter_context(patch.object(owner, member, watched(name, actual, signature)))
        early_memory_worker.worker(request, result, library, "control")
    path = Path(result)
    value = json.loads(path.read_bytes())
    value["metrics"]["prep_stream_measurement"] = dict(
        stages=stages, evidence=evidence, streamed=dict(used)
    )
    if mode == "stream":
        value["boundary"] = prep_stream_sky.BOUNDARY
    save_json(path, value)


if __name__ == "__main__":
    worker(*sys.argv[1:])
