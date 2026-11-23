"""Compare two frozen read-ahead policies at the identical signed DSP workload."""

import argparse
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
from time import perf_counter_ns
from unittest.mock import patch

from . import full_short_cold as full, physical_stage_envelope as physical, public_short_prefetch as public
from . import sparse_cold_input as cold


ORDERS = (("advice", "prefetch"), ("prefetch", "advice"))
REFERENCE = "f8ec74a516fe6682a3f08b133a6a3a180052734ccbcc30f4ef585d9e089d24bf"
RATE_THRESHOLD = 250_000_000


def validate(row, packet, base, chunks, request):
    digests = row["decoded_iq_hashes"]
    counters = row["checked"]["calls"]
    reduced = dict(doc=packet, work=row["checked"], decoded_iq_hashes=digests, native=row["native"])
    physical.verify_result("dsp", reduced, base, request, chunks)
    overlap = row["overlap"]
    if overlap["submitted"] != 1:
        raise ValueError("Expected one next-member operation")
    if row["ingress"] == "prefetch" and (overlap["hits"] != 1 or overlap["fallback"] != 0
                                         or overlap["hit_bytes"] != chunks[-1].compressed_bytes
                                         or row["worker_cpus"] != [2]):
        raise ValueError("Prefetch failed to lend the full original member from the single pinned worker")
    if (counters["compressed_descriptor"] != (1 if row["ingress"] == "prefetch" else 2)
            or row["native"]["native_calls"] != {"full": 32, "short_primary": 224}):
        raise ValueError("Descriptor or receiver schedule differs")
    return {key: reduced[key] for key in ("raw_authority", "metadata_sha256", "probe_sha256", "factors", "probes")}


def measured_rate(compressed, decoded, seconds_ns):
    return dict(compressed_mb_s=1000 * compressed / seconds_ns, decoded_mb_s=1000 * decoded / seconds_ns,
                reaches_250_mb_s=compressed * 10**9 >= RATE_THRESHOLD * seconds_ns)


def worker_run(mode, request_path, binary, output):
    from tools.pipeline_eval.variants.experimental import receiver_member_prefetch as prefetch

    read = prefetch.prefetch_member
    elapsed = []

    def observed(*args):
        start = perf_counter_ns()
        try:
            return read(*args)
        finally:
            elapsed.append(perf_counter_ns()-start)

    with (patch.object(cold, "WINDOWS", physical.WINDOWS), patch.object(cold, "MEMBERS", physical.MEMBERS),
          patch.object(prefetch, "prefetch_member", observed)):
        public.worker(mode, request_path, binary, output)
    full.freeze(output.with_suffix(".worker.json"), dict(elapsed_ns=elapsed))


def run(root, binary, output):
    from tools.pipeline_eval.qualification.cache_residency import load_query
    from leo.contracts.multirate_window_recording import ShortWindowManifestV2

    host = full.check_machine()
    root = root.resolve(strict=True)
    if root.parent != Path("/srv/bulk/leo-dev") or not root.name.startswith("leo-physical-stage-envelope-"):
        raise ValueError("Only the original private physical ladder copy is authorized")
    archived = json.loads(cold.verified(physical.ARCHIVED_DSP, physical.ARCHIVED_DSP_SHA))
    reference = json.loads(gzip.decompress(cold.verified(
        physical.HERE / "measurements/physical-stage-envelope.json.gz", REFERENCE)))
    original = next(r for r in reference["arms"] if r["arm"] == "dsp")
    probes = [p for p in archived["source"]["probes"] if p["visit_index"] < physical.WINDOWS]
    base = dict(probes=probes, metadata=[dict(p, candidates=[]) for p in probes],
                iq=original["decoded_iq_hashes"], clocks=archived["delivery_clocks"][:physical.WINDOWS],
                clock_anchor=archived["clock_anchor"])
    request_path = root / "recovered-request.json"
    request = json.loads(request_path.read_bytes())
    segment = Path(request["entry"]["path"])
    if (segment.parent != root or request["inventory_digest"] != reference["inventory"]
            or request["inventory_digest"] != archived["source"]["input_manifest_sha256"]
            or request["entry"]["manifest_digest"] != "sha256:"+cold.MANIFEST_SHA):
        raise ValueError("Recovered recording authority differs")
    manifest = ShortWindowManifestV2.model_validate_json(cold.verified(segment / "manifest.json", cold.MANIFEST_SHA))
    chunks = tuple(manifest.chunks[:physical.MEMBERS])
    if [c.model_dump(mode="json") for c in chunks] != reference["chunks"]:
        raise ValueError("The already-staged signed members differ")
    payloads = [segment / cold.source_member_name(c.payload_relative_path) for c in chunks]
    indexes = [segment / cold.source_member_name(c.index_relative_path) for c in chunks]
    ids = {path: cold.private_identity(path, root) for path in (*payloads, *indexes)}
    cold.verified(cold.CACHE_LIBRARY, cold.CACHE_SHA)
    query = load_query(cold.CACHE_LIBRARY)

    def cache(paths, *, evict=False):
        return [cold.cache_pages(p, root, ids[p], query, cold=evict) for p in paths]

    output.mkdir()
    rows = []
    compressed = sum(c.compressed_bytes for c in chunks)
    decoded = sum(c.uncompressed_bytes for c in chunks)
    for pair, order in enumerate(ORDERS, start=1):
        for arm in order:
            pressure = Path("/proc/pressure/io").read_text().splitlines()
            initial = cache(payloads, evict=True)
            index_before = cache(indexes)
            if any(initial) or index_before != reference["index_pages"]:
                raise ValueError("The original private payload and index page states differ")
            sealed = output / f"{pair}-{arm}.json"
            command = [sys.executable, "-BPs", "-m", __spec__.name, "worker", arm,
                       request_path, binary, sealed]
            before = resource.getrusage(resource.RUSAGE_CHILDREN)
            start = perf_counter_ns()
            process = subprocess.run(command, check=False, timeout=30)
            wall = perf_counter_ns()-start
            after = resource.getrusage(resource.RUSAGE_CHILDREN)
            timers = dict(process_wall_ns=wall, status=process.returncode,
                          user_cpu_s=after.ru_utime-before.ru_utime, system_cpu_s=after.ru_stime-before.ru_stime,
                          external_input_blocks=after.ru_inblock-before.ru_inblock,
                          voluntary_switches=after.ru_nvcsw-before.ru_nvcsw,
                          involuntary_switches=after.ru_nivcsw-before.ru_nivcsw)
            full.freeze(output / f"{pair}-{arm}.process.json", timers)
            process.check_returncode()
            row = json.loads(sealed.with_suffix(".receipt.json").read_bytes())
            worker = json.loads(sealed.with_suffix(".worker.json").read_bytes())["elapsed_ns"]
            if len(worker) != int(arm == "prefetch"):
                raise ValueError("Unexpected helper thread invocation count")
            packet = json.loads(cold.verified(sealed, row["sealed_detection_sha256"]))
            audit = validate(row, packet, base, chunks, request)
            row.update(pair=pair, process=timers, audit=audit, helper_elapsed_ns=worker, start_payload_pages=initial,
                       end_payload_pages=cache(payloads), start_index_pages=index_before, end_index_pages=cache(indexes),
                       io_pressure_before=pressure, io_pressure_after=Path("/proc/pressure/io").read_text().splitlines(),
                       **measured_rate(compressed, decoded, row["acquire_wall_ns"]))
            rows.append(row)
    digest_set = {row["sealed_detection_sha256"] for row in rows}
    if len(digest_set) != 1 or any(row["audit"]["probe_sha256"] != original["probe_sha256"] for row in rows):
        raise ValueError("Verified acquisition packets differ")
    full.freeze(output / "prefetch.json", dict(machine=host, orders=ORDERS, arms=rows, member_pins=reference["chunks"],
                source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), prefetch_sha256=cold.PREFETCH_SHA,
                physical_reference_sha256=REFERENCE, input_inventory=reference["inventory"],
                compressed_bytes=compressed, decoded_bytes=decoded, new_source_read_bytes=0,
                rate_threshold_bytes_per_second=RATE_THRESHOLD, binary_sha256=full.SHORT_SHA, packet_sha256=digest_set.pop()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    pair = sub.add_parser("run")
    worker = sub.add_parser("worker")
    for name in ("root", "binary", "output"):
        pair.add_argument(name, type=Path)
    worker.add_argument("mode", choices=("advice", "prefetch"))
    for name in ("request_path", "binary", "output"):
        worker.add_argument(name, type=Path)
    kwargs = vars(parser.parse_args())
    if kwargs.pop("command") == "run":
        run(**kwargs)
    else:
        worker_run(**kwargs)
