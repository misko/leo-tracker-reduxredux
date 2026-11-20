"""Trace exact family-confidence phases and the frozen full composed worker."""

import json
import sys
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.qualification.composed_memory_worker import worker as composed
from tools.pipeline_eval.qualification.working_memory_worker import fingerprint, rss
from tools.pipeline_eval.variants import v5_family_memory as fast

FROZEN = {
    "orbit_modes": "778104949ad9467b613ffab820a75db013b33fa86ad810ea00b226841fdc8b52",
    "retained_position": "5d491104a62a78f177a556366168767c5fd62b0dca41c9cf168fe2597f40a81e",
    "family_weighting": "ff20661e8685e49089ba716eb60f05f3596f94c7303e8cc2b90e40dc630a8f31",
}


def cache_inventory(scan):
    return [
        dict(rows=len(key), bytes=sum(a.nbytes for a in record[0].values()))
        for key, record in getattr(scan, "previous_shape_cache", {}).items()
    ]


def instrument(mode):
    from leo.analysis.localization_v3 import (
        family_weighting,
        history_policy,
        orbit_modes,
        retained_position,
    )

    for module in (family_weighting, orbit_modes, retained_position):
        name = module.__name__.rsplit(".", 1)[-1]
        if sha256(Path(module.__file__).read_bytes()).hexdigest() != FROZEN[name]:
            raise ValueError(f"the frozen family prior source {name} differs")

    stock_conf = history_policy.confidence_for
    stock_width = family_weighting.phase_widths
    stock_profile = family_weighting.candidate_profile
    measured = []

    def confidence(scan, *args, **kwargs):
        record = dict(before=rss(), prior_cache_before=cache_inventory(scan), events=[], profiles=0)
        full, ranks = sha256(), sha256()
        measured.append(record)

        def wrapped(operation, label, shape):
            def probe(*a, **kw):
                before, base = rss(), process_time()
                result = operation(*a, **kw)
                entry = dict(
                    stage=label,
                    before=before,
                    after=rss(),
                    cpu_s=process_time() - base,
                    shape=shape(a, result),
                )
                record["events"].append(entry)
                return result

            return probe

        def width(scan_arg, labels):
            operation = fast.width_reader(stock_width) if mode == fast.METHOD else stock_width
            with ExitStack() as prior:
                for name, describe in (
                    (
                        "ecef_states",
                        lambda a, r: dict(
                            rows=len(r[0]), times=len(a[2]), output_bytes=r[0].nbytes + r[1].nbytes
                        ),
                    ),
                    (
                        "phase_shifted_states",
                        lambda a, r: dict(
                            rows=len(r[0]),
                            times=len(a[1]),
                            input_state_bytes=a[0]["position_km"].nbytes
                            + a[0]["velocity_km_s"].nbytes,
                            output_bytes=r[0].nbytes + r[1].nbytes,
                        ),
                    ),
                ):
                    prior.enter_context(
                        patch.object(
                            orbit_modes, name, wrapped(getattr(orbit_modes, name), name, describe)
                        )
                    )
                answer = wrapped(
                    operation,
                    "full_catalogue_widths",
                    lambda a, r: dict(rows=len(a[1]), receipt_sha256=fingerprint(r)),
                )(scan_arg, labels)
            record["prior_cache_after_widths"] = cache_inventory(scan)
            return answer

        def profile(*a, **kw):
            result = stock_profile(*a, **kw)
            record["profiles"] += 1
            full.update(fingerprint(result).encode())
            ranks.update(fingerprint(np.argsort(result["cost"])).encode())
            return result

        began = perf_counter(), process_time()
        with (
            patch.object(family_weighting, "phase_widths", width),
            patch.object(family_weighting, "candidate_profile", profile),
        ):
            vector = stock_conf(scan, *args, **kwargs)
        record.update(
            after=rss(),
            generated_profiles_sha256=full.hexdigest(),
            rank_order_sha256=ranks.hexdigest(),
            confidence_sha256=fingerprint(vector),
            wall_s=perf_counter() - began[0],
            cpu_s=process_time() - began[1],
        )
        numbers = {k: v for k, v in record.items() if k != "prior_cache_before"}
        print("family-allocation: " + json.dumps(numbers, sort_keys=True), flush=True)
        return vector

    return patch.object(history_policy, "confidence_for", confidence), measured


def worker(request, output, library, mode):
    observer, receipt = instrument(mode)
    with observer:
        composed(request, output, library)
    destination = Path(output)
    result = json.loads(destination.read_bytes())
    result["metrics"]["family_memory_audit"] = receipt
    if mode == fast.METHOD:
        result["boundary"] = fast.BOUNDARY
    save_json(destination, result)


if __name__ == "__main__":
    worker(*sys.argv[1:])
