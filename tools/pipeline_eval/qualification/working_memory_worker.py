"""Audit immutable scientific inputs and the early association allocation lifetime."""

import json
import os
import sys
from contextlib import ExitStack
from functools import wraps
from hashlib import sha256
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import perf_counter
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.qualification import secant_end_to_end_worker as measured
from tools.pipeline_eval.variants import v5_discovery_memory as candidate

PAGE_KIB = os.sysconf("SC_PAGE_SIZE") // 1024


def rss():
    current = int(Path("/proc/self/statm").read_text().split()[1]) * PAGE_KIB
    return dict(rss_kib=current, peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss)


def fingerprint(value):
    """Hash ordered FP64 data with array shape/dtype without cloning big buffers."""
    result = sha256()

    def add(item):
        if isinstance(item, np.ndarray):
            result.update(str((item.shape, item.dtype.str)).encode())
            result.update(memoryview(np.ascontiguousarray(item)).cast("B"))
        elif isinstance(item, dict):
            result.update(b"{")
            for key in sorted(item, key=str):
                add(key)
                add(item[key])
            result.update(b"}")
        elif isinstance(item, (list, tuple)):
            result.update(b"[")
            for child in item:
                add(child)
            result.update(b"]")
        else:
            if isinstance(item, np.generic):
                item = item.item()
            result.update(json.dumps(item, sort_keys=True, allow_nan=True).encode())
            result.update(b",")

    add(value)
    return result.hexdigest()


def worker(request, result, library, mode):
    from leo.analysis.localization_v3 import discovery, scan

    from leo.application import localization_v3 as application
    from leo.operations import localization_v3_inputs as inputs

    original_association = scan.ScanLikelihood.association
    original_explore = discovery.explore
    bank, tracks, sky = (
        inputs.regional_bank,
        application.prepare_tracks,
        application.prepare_initial_sky,
    )
    evidence, explorations = {}, []

    @wraps(bank)
    def instrumented_bank(catalogue, *args, **kwargs):
        before = rss()
        wall, cpu = perf_counter(), measured.cpu_s()
        value = bank(catalogue, *args, **kwargs)
        after = rss()
        arrays = value["bank"]
        evidence["regional_bank"] = dict(
            before=before,
            after=after,
            wall_s=perf_counter() - wall,
            cpu_s=measured.cpu_s() - cpu,
            coarse_catalogue=len(catalogue),
            selected=len(value["source_indices"]),
            source_indices_sha256=fingerprint(value["source_indices"]),
            selected_source_indices=value["source_indices"].tolist(),
            selected_norad=arrays["norad"].tolist(),
            arrays_sha256={key: fingerprint(array) for key, array in arrays.items()},
            fine_bank_payload_bytes=sum(array.nbytes for array in arrays.values()),
        )
        return value

    @wraps(sky)
    def instrumented_sky(*args, **kwargs):
        before = rss()
        wall, cpu = perf_counter(), measured.cpu_s()
        value = sky(*args, **kwargs)
        evidence["prepare_initial_sky"] = dict(
            before=before,
            after=rss(),
            wall_s=perf_counter() - wall,
            cpu_s=measured.cpu_s() - cpu,
            candidate_count=value["metadata"]["candidate_count"],
            causal_elements_sha256=fingerprint(value["nominal_elements"]),
            previous_elements_sha256=value["previous_receipt"]["catalogue_sha256"],
            genuine_previous_elements_sha256=value["genuine_previous_receipt"]["catalogue_sha256"],
        )
        return value

    @wraps(tracks)
    def instrumented_tracks(*args, **kwargs):
        value = tracks(*args, **kwargs)
        evidence["track_sha256"] = fingerprint(value["tracks"])
        evidence["observation_sha256"] = fingerprint(value["observations"])
        return value

    @wraps(original_association)
    def association(self, *args, **kwargs):
        if not explorations or explorations[-1].get("complete"):
            return original_association(self, *args, **kwargs)
        events = explorations[-1]["computed"]
        before = rss()
        wall, cpu = perf_counter(), measured.cpu_s()
        value = original_association(self, *args, **kwargs)
        elapsed, cpu_elapsed, after = perf_counter() - wall, measured.cpu_s() - cpu, rss()
        rows, nominations, projection = value[1:]
        arrays = dict(
            predicted_payload_bytes=sum(a.nbytes for a in projection),
            diagnostic_payload_bytes=sum(
                n["terms"][k].nbytes
                for n in nominations.values()
                for k in ("residual", "innovations")
            ),
        )
        events.append(dict(before=before, after=after, wall_s=elapsed, cpu_s=cpu_elapsed, **arrays))
        if len(events) == 1:
            explorations[-1]["first_rows_sha256"] = fingerprint(rows)
            explorations[-1]["projected_visibility_sha256"] = fingerprint(projection[1])
        return value

    @wraps(original_explore)
    def explore(*args, **kwargs):
        trace = dict(before=rss(), computed=[])
        explorations.append(trace)
        value = original_explore(*args, **kwargs)
        trace.update(after=rss(), complete=True, output_sha256=fingerprint(value))
        return value

    with ExitStack() as stack:
        stack.enter_context(patch.object(inputs, "regional_bank", instrumented_bank))
        stack.enter_context(patch.object(application, "prepare_initial_sky", instrumented_sky))
        stack.enter_context(patch.object(application, "prepare_tracks", instrumented_tracks))
        stack.enter_context(patch.object(discovery, "explore", explore))
        stack.enter_context(patch.object(scan.ScanLikelihood, "association", association))
        reuse = (
            stack.enter_context(candidate.reuse_discovery_association())
            if mode == "candidate"
            else {}
        )
        measured.worker(request, result, library, "secant")
    path = Path(result)
    response = json.loads(path.read_bytes())
    response["metrics"]["working_memory"] = dict(
        evidence, explorations=explorations, reuse=dict(reuse)
    )
    if mode == "candidate":
        response["boundary"] = candidate.BOUNDARY
    save_json(path, response)


if __name__ == "__main__":
    worker(*sys.argv[1:])
