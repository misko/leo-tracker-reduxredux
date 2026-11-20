"""Stream archived winning GLRT peaks into a bounded Graph-to-position worker."""

import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from resource import RLIMIT_AS, RUSAGE_SELF, getrusage, setrlimit
from time import perf_counter, process_time

BOUNDARY = "Authenticated stored GLRT peaks through one-pass Graph and exact robust positioning"
CONTROL_BOUNDARY = "Anonymous tracks through the same exact robust positioning backend"
METHOD = "native_lean"
CONTROL = "native_lean_prepared"
RSS_TARGET_MIB = 256
AS_LIMIT_MIB = 512
BLOCK_BYTES = 64 * 1024
ARCHIVE_LIMIT = 64 * 1024 * 1024
CATALOGUE_LIMIT = 4 * 1024 * 1024
WHITENING_LIMIT = 32 * 1024 * 1024


class VerifiedBlocks:
    """Hash the same binary blocks supplied to the compact archive reader."""

    def __init__(self, stream):
        self.stream = stream
        self.digest = hashlib.sha256()
        self.bytes = 0

    def read(self, size):
        if not 0 < size <= BLOCK_BYTES:
            raise ValueError("expected a bounded archive read")
        block = self.stream.read(size)
        self.bytes += len(block)
        if self.bytes > ARCHIVE_LIMIT:
            raise ValueError("native archive exceeds the worker byte budget")
        self.digest.update(block)
        return block.decode("ascii")

    def finish(self, expected):
        while self.read(BLOCK_BYTES):
            pass
        if self.digest.hexdigest() != expected:
            raise ValueError("native GLRT archive differs from its declared digest")


def _load(record, limit):
    with Path(record["path"]).open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit or hashlib.sha256(raw).hexdigest() != record["sha256"]:
        raise ValueError("bound reader input exceeds its budget or differs from its digest")
    return raw


def peak_lanes(record, probe_limit, cutoff):
    from tools.pipeline_eval.reference.native_archive import NativeArchive

    lanes = defaultdict(list)
    receiver_end = {}
    probes = winners = 0
    with Path(record["path"]).open("rb") as stream:
        reader = VerifiedBlocks(stream)
        archive = NativeArchive(reader)
        meta = archive.meta
        duration = meta["duration_s"]
        if (
            not 0 < duration <= 360
            or archive.probe_s != 0.02
            or meta["causal_cutoff_utc_ns"] != cutoff
            or not 0 <= meta["anchor_utc_ns"] - cutoff <= 1_000_000_000
        ):
            raise ValueError("native archive is outside the declared short-scan clock domain")
        for at, text in archive:
            probes += 1
            if probes > probe_limit:
                raise ValueError("native archive exceeds its bound probe count")
            row = json.loads(text)
            rx, channel = row["receiver_id"], row["channel"]
            rf, start = row["actual_rf_hz"], row["valid_start_counter"]
            if (
                rx not in (0, 1)
                or channel not in range(1, 9)
                or not 1e9 < rf < 100e9
                or start < receiver_end.get(rx, archive.first)
                or not 0.01 - 1e-8 <= at <= duration - 0.01 + 1e-8
                or len(row["candidates"]) > 8
            ):
                raise ValueError("invalid or overlapping native receiver support")
            receiver_end[rx] = start + 200_000
            accepted = [c for c in row["candidates"] if c["passed_fractional_margin_gate"] is True]
            if not accepted:
                continue
            winner = max(accepted, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]))
            frequency = winner["fractional_tracking_cfo_hz"]
            if not math.isfinite(frequency) or not math.isfinite(winner["fractional_margin"]):
                raise ValueError("nonfinite winning candidate")
            lanes[rf, rx + 1, channel].append((at, frequency))
            winners += 1
            if len(lanes) > 16:
                raise ValueError("native archive exceeds the dual-receiver lane budget")
        reader.finish(record["sha256"])
    if set(receiver_end) != {0, 1}:
        raise ValueError("native archive must contain both original receivers")
    clock = dict(anchor_utc_ns=meta["anchor_utc_ns"], cutoff_utc_ns=cutoff, duration_s=duration)
    return clock, lanes, dict(native_bytes=reader.bytes, probes=probes, winning_peaks=winners)


def graph_projection(lanes, configuration):
    import numpy as np

    from leo.analysis.graph_tracklets import fit_lane
    from leo.analysis.polynomial_tracklets import TrackConfig

    config = TrackConfig(**configuration)
    tracks = []
    for (rf, receiver, channel), points in sorted(lanes.items()):
        t, y = np.asarray(points, dtype=np.float64).T
        result = fit_lane(t, y, config)
        for track in result["tracks"]:
            indexes = np.asarray(track["indices"], dtype=int)
            indexes = indexes[np.argsort(t[indexes], kind="stable")]
            values = y[indexes] + config.alias_spacing_hz * result["alias_lifts"][indexes]
            tracks.append(
                dict(
                    times=t[indexes].tolist(),
                    values=values.tolist(),
                    receiver=receiver,
                    channel=channel,
                    rf_hz=rf,
                )
            )
    return tracks


def projection_digest(observation):
    payload = json.dumps(observation, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _now():
    return perf_counter(), process_time()


def _elapsed(start):
    return dict(wall_s=perf_counter() - start[0], cpu_s=process_time() - start[1])


def worker(request):
    setrlimit(RLIMIT_AS, (AS_LIMIT_MIB * 1024**2, AS_LIMIT_MIB * 1024**2))
    start = _now()
    from tools.pipeline_eval.variants import robust_orbit_fit

    phases = {"backend_import": _elapsed(start)}
    start = _now()
    catalogue = _load(request["catalogue"], CATALOGUE_LIMIT).decode("ascii")
    phases["catalogue_read"] = _elapsed(start)
    counts = {}
    start = _now()
    if request["mode"] == "native":
        clock, lanes, counts = peak_lanes(
            request["native"], request["probe_limit"], request["cutoff"]
        )
        phases["archive_and_peak_selection"] = _elapsed(start)
        start = _now()
        config = json.loads(_load(request["track_config"], BLOCK_BYTES))["config"]
        tracks = graph_projection(lanes, config)
        del lanes
        observation = dict(clock, tracks=tracks, catalog_timestamp_ns=request["catalog_timestamp"])
        phases["graph"] = _elapsed(start)
    elif request["mode"] == "prepared":
        observation = json.loads(_load(request["observation"], ARCHIVE_LIMIT))
        phases["prepared_track_read"] = _elapsed(start)
    else:
        raise ValueError("unknown measured input boundary")
    if (
        observation["cutoff_utc_ns"] != request["cutoff"]
        or observation["catalog_timestamp_ns"] != request["catalog_timestamp"]
    ):
        raise ValueError("observation and catalogue time authorities differ")
    counts["whitening_matrix_byte_bound"] = 8 * sum(
        len(t["times"]) ** 2 for t in observation["tracks"]
    )
    if counts["whitening_matrix_byte_bound"] > WHITENING_LIMIT:
        raise ValueError("track whitening exceeds the worker array budget")
    observed = projection_digest(observation)
    start = _now()
    result = robust_orbit_fit.infer(observation, request["offer"], catalogue)
    phases["same_exact_backend"] = _elapsed(start)
    result["boundary"] = BOUNDARY if request["mode"] == "native" else CONTROL_BOUNDARY
    inventory = sorted(
        {
            path
            for module in tuple(sys.modules.values())
            if (path := getattr(module, "__file__", ""))
            and path.endswith(".py")
            and path.startswith(("/source/", "/worker/"))
        }
    )
    memory = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in ("VmHWM", "VmPeak"):
            memory[key] = int(value.split()[0])
    return dict(
        result=result,
        stages=phases,
        counts=counts,
        observation_sha256=observed,
        resident_peak_kib=getrusage(RUSAGE_SELF).ru_maxrss,
        address_space_limit_mib=AS_LIMIT_MIB,
        proc_memory_kib=memory,
        imported_first_party=inventory,
    )


if __name__ == "__main__":
    started = _now()
    receipt = worker(json.load(sys.stdin))
    receipt["worker"] = _elapsed(started)
    json.dump(receipt, sys.stdout, sort_keys=True, allow_nan=False)
