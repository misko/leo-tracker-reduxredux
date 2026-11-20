"""Rebuild compact v5 from a contiguous causal prefix of native receiver factors."""

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

from tools.pipeline_eval.variants import orbit_projector, v5_core, v5_lean

PREFIX_SECONDS = 180
POLICY = "contiguous-native-counter-prefix/v1"
BOUNDARY = "Contiguous native detector factors through causal Graph and compact v5 cavity"


def _identity(value):
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
    )


def restrict(document, *, prefix):
    """Validate complete visit support and return the original or a strict prefix document."""
    source, provenance, anchor = (document[k] for k in ("source", "provenance", "clock_anchor"))
    clocks = document["delivery_clocks"]
    rate, first = source["sample_rate_hz"], anchor["sample_counter"]
    window = rate * source["probe_ms"] // 1000
    count, terminal = provenance["window_count"], document["last_sample_counter"]
    if (
        len(clocks) != count
        or not clocks
        or rate != 10_000_000
        or source["probe_ms"] != 20
        or anchor["after"] != clocks[0]
        or terminal <= first + rate * PREFIX_SECONDS
    ):
        raise ValueError(
            "expected complete 10 MHz capture with original UTC and delivery authority"
        )

    by_visit = defaultdict(list)
    for probe in source["probes"]:
        by_visit[probe["visit_index"]].append(probe)
    invalid = {row["visit"]: row for row in provenance["excluded_windows"]}
    if (
        len(invalid) != provenance["invalid_capture"]
        or len(by_visit) != provenance["processed_windows"]
        or by_visit.keys() & invalid.keys()
        or by_visit.keys() | invalid.keys() != set(range(count))
    ):
        raise ValueError("probe and exclusion receipts must cover every scheduled visit")

    samples = []
    end = first
    for i in range(count):
        if i in invalid:
            start, stop = (invalid[i][k] for k in ("sample_start", "sample_end"))
        else:
            probes = by_visit[i]
            start = probes[0]["valid_start_counter"]
            stop = start + window
            if (
                len(probes) != 2
                or {p["receiver_id"] for p in probes} != {0, 1}
                or any(
                    p["channel"] != i % 8 + 1
                    or p["valid_start_counter"] != start
                    or p["probe_start_ms"] != 0
                    or p["probe_index"] != 0
                    for p in probes
                )
            ):
                raise ValueError("expected original paired probes and eight-channel cadence")
        if start < end or stop - start != window or (i == 0 and start != first):
            raise ValueError("sample traversal differs from the original acquisition clock")
        end = stop
        samples.append(stop)
    if end != terminal or any(
        a["monotonic_ns"] >= b["monotonic_ns"] for a, b in zip(clocks, clocks[1:], strict=False)
    ):
        raise ValueError("recording counters and delivery timestamps must close in order")

    cutoff = first + rate * PREFIX_SECONDS
    if prefix:
        kept = sum(end <= cutoff for end in samples)
        probes = [p for p in source["probes"] if p["visit_index"] < kept]
        excluded = [row for row in provenance["excluded_windows"] if row["visit"] < kept]
        identity = _identity([POLICY, cutoff, source["analysis_manifest_sha256"], probes, excluded])
        document = dict(
            document,
            source=dict(source, analysis_manifest_sha256=identity, probes=probes),
            delivery_clocks=clocks[:kept],
            last_sample_counter=samples[kept - 1],
            provenance=dict(
                provenance,
                run_id="prefix-" + identity[7:39],
                scope=POLICY,
                window_count=kept,
                invalid_capture=len(excluded),
                excluded_windows=excluded,
                processed_windows=kept - len(excluded),
            ),
        )
    else:
        kept, probes, excluded = count, source["probes"], provenance["excluded_windows"]
    start_offsets = [anchor[k]["monotonic_ns"] for k in ("after", "before")]
    delivery = clocks[kept - 1]["monotonic_ns"]
    return document, dict(
        scope="prefix" if prefix else "full",
        scheduled_visits=kept,
        original_scheduled_visits=count,
        valid_visits=kept - len(excluded),
        excluded_visits=len(excluded),
        actual_channels=sorted({p["channel"] for p in probes}),
        original_start_counter=first,
        prefix_cutoff_counter=cutoff,
        last_sample_counter=samples[kept - 1],
        next_sample_end_counter=samples[kept] if kept < count else None,
        last_input_sample_s=(samples[kept - 1] - first) / rate,
        last_host_delivery_ns=delivery,
        last_input_delivery_elapsed_s=[(delivery - start) / 1e9 for start in start_offsets],
        full_input_delivery_elapsed_s=[
            (clocks[-1]["monotonic_ns"] - start) / 1e9 for start in start_offsets
        ],
        before_bracket_utc_ns=anchor["before"]["realtime_ns"],
        after_bracket_utc_ns=anchor["after"]["realtime_ns"],
    )


def audit_prepared(prepared):
    """Confirm the rebuilt tracks and the initial sky respect their frozen time authority."""
    if "tracks" not in prepared:
        return {}
    tracks = prepared["tracks"]
    meta = tracks["metadata"]
    observation_end = max((row["time_s"] for row in tracks["observations"]), default=0.0)
    track_end = max((row["end_s"] for row in tracks["tracks"]), default=0.0)
    if not 0 <= track_end <= observation_end <= meta["duration_s"]:
        raise ValueError("prepared evidence exceeds the retained capture end")
    audit = dict(
        latest_observation_s=observation_end,
        latest_track_s=track_end,
        prepared_duration_s=meta["duration_s"],
        causal_cutoff_utc_ns=meta["causal_cutoff_utc_ns"],
    )
    if "sky" in prepared:
        sky = prepared["sky"]
        cutoff = meta["causal_cutoff_utc_ns"]
        evidence = [
            timestamp
            for row in sky["nominal_elements"].values()
            for timestamp in (
                row["provenance"]["collected_utc_ns"],
                row["provenance"]["element_epoch_utc_ns"],
            )
        ]
        audit.update(
            catalogue_candidates=sky["metadata"]["candidate_count"],
            catalogue_latest_sha256="sha256:"
            + hashlib.sha256(sky["selected_tle"].encode()).hexdigest(),
            latest_catalogue_authority_utc_ns=max(evidence),
        )
        if sky["metadata"]["cutoff_utc_ns"] != cutoff or max(evidence) > cutoff:
            raise ValueError("prepared sky exceeds the original capture-start causal cutoff")
    return audit


def worker(request, result, library):
    original = v5_core.infer

    def infer(prepared, *args):
        audit = audit_prepared(prepared)
        result = original(prepared, *args)
        result["metrics"].update(audit)
        return result

    with patch.object(v5_core, "infer", infer):
        orbit_projector.worker(request, result, library)


def run(case, work_dir):
    library = Path(work_dir) / "orbit_projector.so"
    library.parent.mkdir(parents=True, exist_ok=True)
    orbit_projector.compile_kernel(library)
    result = v5_lean.run_bound_worker(case, work_dir, Path(__file__), worker_args=(str(library),))
    result["boundary"] = BOUNDARY
    return result


if __name__ == "__main__":
    worker(*sys.argv[1:])
