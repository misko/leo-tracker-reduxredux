"""Retain alternate complete archived sweeps through the paired v5 cavity fit."""

import gzip
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from tools.pipeline_eval.variants import v5_lean

CHANNELS = tuple(range(1, 9))
METHOD = "sweep_schedule"
BOUNDARY = "Alternating complete archived GLRT sweeps to the paired v5 cavity positions"
CAVITY_SHA256 = "0055466f87b16942f8b83e6ebdbf177be1ff6a8f1bb43c649d4f55733c1822e4"


def scheduled(visit, complete_sweeps):
    return visit // len(CHANNELS) < complete_sweeps and visit // len(CHANNELS) % 2 == 0


def selected_probes(document):
    source, provenance = document["source"], document["provenance"]
    clocks, count = document["delivery_clocks"], provenance["window_count"]
    if type(count) is not int or count < 0 or len(clocks) != count:
        raise ValueError("expected one delivery clock per global visit")
    receivers = defaultdict(set)
    for row in source["probes"]:
        visit, channel, receiver = (row[k] for k in ("visit_index", "channel", "receiver_id"))
        if (
            type(visit) is not int
            or not 0 <= visit < count
            or type(channel) is not int
            or channel != CHANNELS[visit % len(CHANNELS)]
        ):
            raise ValueError("archive does not use the expected eight-channel sweep order")
        if receiver in receivers[visit]:
            raise ValueError("a visit contains duplicate receiver evidence")
        receivers[visit].add(receiver)
    if any(rx != {0, 1} for rx in receivers.values()):
        raise ValueError("expected both recorded receivers on every processed visit")
    exclusions = provenance["excluded_windows"]
    excluded = {row["visit"]: row["reason"] for row in exclusions}
    if (
        len(excluded) != len(exclusions)
        or len(receivers) != provenance["processed_windows"]
        or receivers.keys() & excluded.keys()
        or receivers.keys() | excluded.keys() != set(range(count))
    ):
        raise ValueError("processed and excluded visits do not account for the archive")

    complete, trailing = divmod(count, len(CHANNELS))
    keep = {i for i in range(count) if scheduled(i, complete)}
    kept_processed = keep & receivers.keys()
    kept = [row for row in source["probes"] if row["visit_index"] in kept_processed]
    retained_times = [clocks[i]["realtime_ns"] for i in sorted(keep)]
    duration = (clocks[-1]["realtime_ns"] - clocks[0]["realtime_ns"]) / 1e9 if clocks else 0.0
    span = (retained_times[-1] - retained_times[0]) / 1e9 if retained_times else 0.0
    original_channels = Counter(CHANNELS[i % len(CHANNELS)] for i in receivers)
    kept_channels = Counter(CHANNELS[i % len(CHANNELS)] for i in kept_processed)
    metrics = dict(
        schedule=METHOD,
        complete_sweeps=complete,
        kept_complete_sweeps=(complete + 1) // 2,
        trailing_partial_visits=trailing,
        original_scheduled_visits=count,
        kept_scheduled_visits=len(keep),
        original_processed_visits=len(receivers),
        kept_processed_visits=len(kept_processed),
        original_exclusions=dict(Counter(excluded.values())),
        kept_exclusions=dict(Counter(excluded[i] for i in keep & excluded.keys())),
        original_processed_by_channel=[original_channels[c] for c in CHANNELS],
        kept_processed_by_channel=[kept_channels[c] for c in CHANNELS],
        original_probes=len(source["probes"]),
        kept_probes=len(kept),
        original_delivery_span_s=duration,
        kept_delivery_span_s=span,
    )
    return dict(document, source=dict(source, probes=kept)), metrics


def track_support(full, half):
    """Measure observation loss and track recovery using stable native observation IDs."""
    kept_ids = {row["observation_id"] for row in half["observations"]}
    owner = {
        obs: index for index, track in enumerate(half["tracks"]) for obs in track["observation_ids"]
    }
    support = []
    for track in full["tracks"]:
        original = set(track["observation_ids"])
        retained = original & kept_ids
        matches = Counter(owner[obs] for obs in retained if obs in owner)
        support.append(
            dict(
                full_points=len(original),
                retained_points=len(retained),
                retracked_points=sum(matches.values()),
                largest_overlap=max(matches.values(), default=0),
                retracked_fragments=len(matches),
            )
        )
    return dict(
        full_observations=len(full["observations"]),
        half_observations=len(half["observations"]),
        full_curved_tracks=len(full["curved_indices"]),
        half_curved_tracks=len(half["curved_indices"]),
        full_graph_points=full["graph_points"],
        half_graph_points=half["graph_points"],
        full_track_support=support,
        half_track_sizes=[len(track["observation_ids"]) for track in half["tracks"]],
    )


def cavity_source(path):
    path = Path(path)
    raw = path.read_bytes()
    source = gzip.decompress(raw) if path.suffix == ".gz" else raw
    if hashlib.sha256(source).hexdigest() != CAVITY_SHA256:
        raise ValueError("cavity solver does not match the archived control")
    return source


def worker(request, result, cavity):
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.operations.localization_v3_job import read_bound

    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.operations import localization_v3_inputs

    core = ModuleType("v5_core_archived")
    core.__file__ = str(cavity)
    exec(compile(cavity_source(cavity), core.__file__, "exec"), vars(core))
    original_infer = core.infer
    original_bank = localization_v3_inputs.regional_bank
    job = json.loads(Path(request).read_bytes())["job"]
    config = TrackConfig(**read_bound(job["track_config"])["config"])
    full, full_duration = None, None

    def select(document):
        nonlocal full, full_duration
        restricted, metrics = selected_probes(document)
        if not restricted["source"]["probes"]:
            return restricted, metrics
        full = prepare_tracks(document, config)
        latest_track_s = max((float(t["times"][-1]) for t in full["tracks"]), default=0.0)
        full_duration = max(300.0, latest_track_s)
        return restricted, metrics

    def orbit_bank(catalogue, origin, _duration, **kwargs):
        return original_bank(catalogue, origin, full_duration, **kwargs)

    def infer(prepared, *args):
        outcome = original_infer(prepared, *args)
        metrics = outcome["metrics"]
        metrics.update(cavity_sha256=CAVITY_SHA256, full_orbit_screen_duration_s=full_duration)
        if tracks := prepared.get("tracks"):
            metrics.update(track_support(full, tracks))
        if sky := prepared.get("sky"):
            metrics.update(
                causal_candidates=sky["metadata"]["candidate_count"],
                causal_catalogue_sha256=hashlib.sha256(sky["selected_tle"].encode()).hexdigest(),
            )
        return outcome

    with (
        patch.object(core, "infer", infer),
        patch.object(localization_v3_inputs, "regional_bank", orbit_bank),
    ):
        core.worker(request, result, select_document=select)


def run(case, work_dir, cavity=None):
    if cavity is None:
        cavity = (
            Path(__file__).resolve().parents[3]
            / "reports/2026_11_19_receiver_streaming/sweep/cavity-source.py.gz"
        )
    result = v5_lean.run_bound_worker(
        case, work_dir, Path(__file__), worker_args=(str(Path(cavity).resolve()),)
    )
    result["boundary"] = BOUNDARY
    return result


if __name__ == "__main__":
    worker(*sys.argv[1:])
