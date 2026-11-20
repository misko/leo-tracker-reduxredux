"""Measure the production composition and trace the same stages under a memory cap."""

import json
import sys
from contextlib import ExitStack
from functools import wraps
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.qualification.working_memory_worker import fingerprint, rss
from tools.pipeline_eval.variants import v5_composed_memory, v5_core, v5_tiled_salvage


def worker(request, result, library):
    from leo.analysis.localization_v3 import (
        conservative_recovery,
        discovery,
        family_cavity,
        history_policy,
        reassociation_admission,
        reassociation_catalogue,
        residual_screen,
        scan,
    )

    from leo.application import localization_v3 as application

    stages, evidence = [], {}

    def watch(operation, name, proof):
        @wraps(operation)
        def wrapped(*args, **kwargs):
            print("stage: enter " + name, flush=True)
            before = rss()
            t, c = perf_counter(), process_time()
            value = operation(*args, **kwargs)
            stages.append(
                dict(
                    stage=name,
                    before=before,
                    after=rss(),
                    wall_s=perf_counter() - t,
                    cpu_s=process_time() - c,
                )
            )
            print("stage: leave " + name, flush=True)
            if proof is not None:
                evidence.setdefault(name, []).append(proof(value))
            return value

        return wrapped

    def graph(value):
        return fingerprint(
            (value["tracks"], value["observations"], value["metadata"], value["curved_indices"])
        )

    def sky(value):
        return dict(
            data=fingerprint(value["bank"]),
            priors=fingerprint({k: v for k, v in value.items() if k != "bank"}),
        )

    before, t, c = rss(), perf_counter(), process_time()
    with ExitStack() as stack:
        for owner, name, proof in (
            (application, "prepare_tracks", graph),
            (application, "prepare_initial_sky", sky),
            (application, "prepare_phase_history", fingerprint),
            (application, "forecast", fingerprint),
            (application, "estimate_noise", fingerprint),
            (application, "prepare_native_scan", None),
            (v5_core, "scan_context", None),
            (v5_core, "initial_selection", None),
            (v5_core, "ranked_initial_nodes", fingerprint),
            (discovery, "fresh_discovery", None),
            (discovery, "statistics", None),
            (discovery, "augment_phase_statistics", None),
            (scan.ScanLikelihood, "association", None),
            (v5_tiled_salvage, "salvage", fingerprint),
            (conservative_recovery, "conservative_recovery", None),
            (history_policy, "confidence_for", fingerprint),
            (history_policy, "history_policy", None),
            (family_cavity, "nominate_families", None),
            (residual_screen, "screen_candidates", fingerprint),
            (reassociation_admission, "screen", fingerprint),
            (reassociation_catalogue, "audit", fingerprint),
            (application, "screen_reassociation_candidates", None),
            (application, "fit_reassociation", None),
        ):
            stack.enter_context(patch.object(owner, name, watch(getattr(owner, name), name, proof)))
        v5_composed_memory.worker(request, result, library)
    path = Path(result)
    value = json.loads(path.read_bytes())
    value["metrics"]["composed_memory_measurement"] = dict(
        before=before,
        after=rss(),
        cpu_s=process_time() - c,
        wall_s=perf_counter() - t,
        stages=stages,
        evidence=evidence,
    )
    save_json(path, value)


if __name__ == "__main__":
    worker(*sys.argv[1:])
