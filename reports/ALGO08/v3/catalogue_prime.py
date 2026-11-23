"""Measure manifest-only priming of the named ALGO08v3 parser on a saved input."""

import argparse
import json
import os
import resource
import subprocess
import sys
from collections import Counter
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
INSTALL = Path("/opt/leo-algo08/algo08v3")
REQUEST = Path("/dev/shm/leo-v3-provisional-salvage-dense-01/request.json")
REQUEST_PIN = "4b6d07ea28051a4ac70030bd20f5da7e8f3bb8187dc84ea4b73fbbb6d04f94f5"
NATIVE_PIN = "ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85"
SPEC_PIN = "6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f"
TRACK_PIN = "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"
HOUR_NS = 3_600_000_000_000
MAX_BODIES = 32
MAX_BYTES = 96 * 1024**2


def checked(path, expected):
    body = path.read_bytes()
    if sha256(body).hexdigest() != expected.removeprefix("sha256:"):
        raise ValueError(f"Unexpected input digest: {path}")
    return body


def select_sources(refs, expected_cutoff):
    """Follow the 48/72 h source order while visiting each immutable body once."""
    recent = [ref for ref in refs if 0 <= expected_cutoff - ref.collected_utc_ns <= 48 * HOUR_NS]
    history = [ref for ref in refs if 0 <= expected_cutoff - ref.collected_utc_ns <= 72 * HOUR_NS]
    unique = {}
    for ref in (*recent, *history):
        unique.setdefault(ref.sha256, ref)
    return tuple(unique.values())


def prime_sources(reader, parser, manifest_path, manifest_digest):
    """Seed only the content-keyed parser. The consumer uses its own cutoff and reads."""
    from leo.contracts.multirate_window_recording import ShortWindowManifestV2

    manifest = ShortWindowManifestV2.model_validate_json(checked(manifest_path, manifest_digest))
    refs = select_sources(reader.list_snapshots("space-track"), manifest.created_utc_ns)
    if len(refs) > MAX_BODIES or sum(ref.byte_size for ref in refs) > MAX_BYTES:
        raise ValueError("Catalogue priming exceeds the frozen work bound")
    for ref in refs:
        parser(reader.read(ref))
    return dict(expected_cutoff_utc_ns=manifest.created_utc_ns,
                finalized_utc_ns=manifest.finalized_utc_ns,
                refs=[ref.path.name for ref in refs], digests=[ref.sha256 for ref in refs],
                bytes=sum(ref.byte_size for ref in refs))


def clock():
    return perf_counter_ns(), process_time_ns(), resource.getrusage(resource.RUSAGE_SELF).ru_inblock


def elapsed(start):
    return dict(zip(("wall_ns", "cpu_ns", "input_blocks"),
                    (end - begin for begin, end in zip(start, clock(), strict=True)), strict=True))


def save(path, result):
    with path.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def check_machine():
    threads = {name: os.environ.get(name) for name in (
        "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    )}
    cpu = sorted(os.sched_getaffinity(0))
    nice = os.getpriority(os.PRIO_PROCESS, 0)
    ionice = subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip()
    if cpu != [2] or nice < 15 or "prio 7" not in ionice or set(threads.values()) != {"1"}:
        raise ValueError("Expected the low-priority single-core Gauss benchmark slot")
    return dict(cpu=cpu, nice=nice, ionice=ionice, threads=threads)


def parsed_witness(parser):
    """Compare exact parser ordering, epochs, line pairs and SGP4 export for each body."""
    from leo.contracts.digests import canonical_digest
    from sgp4.exporter import export_tle

    exports = {id(sat): export_tle(sat) for _, sat, _ in parser.elements.values()}
    bodies = {sha256(text.encode("ascii")).hexdigest(): canonical_digest([
        cat.names, cat.satellite_numbers, cat.epochs, [exports[id(sat)] for sat in cat.satellites],
    ]) for text, cat in parser.catalogues.items()}
    return dict(bodies=bodies, original_line_pairs_sha256=canonical_digest(sorted(parser.elements)))


def worker(mode, output):
    from importlib.util import find_spec
    from runpy import run_path

    host = check_machine()
    payload = INSTALL / "payload"
    spec = run_path(str(INSTALL / "run"))["checked_spec"](payload, SPEC_PIN)
    from tools.pipeline_eval.variants.experimental import lean_startup

    lean_startup.install()
    from leo.application.localization_v3_engine import _prepared_values
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position
    from tools.pipeline_eval.variants import algo08_causal_reuse as reuse
    from tools.pipeline_eval.variants.algo08_causal_table import causal_table
    from tools.pipeline_eval.variants.experimental.graph_path import native_paths
    from tools.pipeline_eval.variants.experimental.preparation_gc import defer_collection
    from tools.pipeline_eval.variants.experimental.tle_records import batch_records

    from reports.ALGO08.v3.paid_certified_trial import prepared_digest

    for module in (algo08_position.__name__, reuse.__name__, causal_table.__module__,
                   native_paths.__module__, defer_collection.__module__, batch_records.__module__):
        module_path = module.replace(".", "/") + ".py"
        if Path(find_spec(module).origin).resolve() != payload / module_path:
            raise ValueError(f"Expected the signed installed module: {module}")
    request = json.loads(checked(REQUEST, REQUEST_PIN))
    location = request["local_archive"]
    archive = TleArchiveReader(Path(location["root"]))
    refs = archive.list_snapshots("space-track")
    archive_digest = canonical_digest({ref.path.name: ref.sha256 for ref in refs})
    if archive_digest != location["snapshots_sha256"]:
        raise ValueError("Saved causal archive changed")
    manifest_path, manifest_digest = request["manifests"][0]
    manifest_path = Path(manifest_path)
    if manifest_path.name != "manifest.json" or manifest_path.parent.parent != Path(request["recording"]):
        raise ValueError("Expected only the first pinned manifest under the original recording")

    timings, reads, calls = {}, {}, {}
    preparation_stats = {}
    parser = reuse.CausalPreparationParser()
    parse_record = reuse.CausalPreparationParser.__call__
    original_read = archive.read
    phase = "prime"

    def observe_read(ref):
        start = clock()
        result = original_read(ref)
        measure = elapsed(start)
        reads[phase]["calls"] += 1
        reads[phase]["bytes"] += ref.byte_size
        reads[phase].update(measure)
        reads[phase + "_refs"].append(ref.path.name)
        return result

    def observe_parse(value, text):
        if value is not parser:
            raise ValueError("The first consumer constructed an unbound parser")
        hit = text in parser.catalogues
        phase_calls = calls[phase]
        start = clock()
        result = parse_record(value, text)
        phase_calls["hits" if hit else "misses"] += 1
        phase_calls.update(elapsed(start))
        return result

    for stage in ("prime", "consumer"):
        reads[stage], reads[stage + "_refs"], calls[stage] = Counter(), [], Counter()
    # Match the installed scope: collection deferred for each preparation and native C parsing.
    original_prepare = defer_collection(algo08_position.prepare_native_scan)
    prime = {}
    with (
        batch_records(Path(spec["tle_parser"]["library"])) as native_counts,
        native_paths(Path(spec["graph_path"]["library"]), required=True) as graph_counts,
        causal_table(canonical_exports=True, previous_catalogues=True) as catalogue_counts,
        patch.object(archive, "read", observe_read),
        patch.object(type(parser), "__call__", observe_parse),
    ):
        start = clock()
        if mode == "primed":
            prime = defer_collection(prime_sources)(archive, parser, manifest_path, manifest_digest)
        timings["prime"] = elapsed(start)
        prime_native = dict(native_counts)
        parser_before = parser.stats.copy()

        # The priming function never received the saved packet, offer or hardware cutoff.
        native = json.loads(checked(Path(request["native_file"]), NATIVE_PIN))
        source = native["source"]
        cutoff = native["clock_anchor"]["before"]["realtime_ns"]
        if (cutoff != request["causal_cutoff_utc_ns"] or source["session_id"] != request["session"]
                or source["input_manifest_sha256"] != request["inventory"]
                or source["raw_recording_authority_digest"] != request["raw_authority"]):
            raise ValueError("The saved packet does not bind to the actual causal cutoff")
        offer = Algo08Region.parse(json.loads(checked(Path(request["offer_file"]), request["offer_sha256"])))
        config = algo08_position.TrackConfig(**json.loads(checked(RELEASE / "assets/tracks.json", TRACK_PIN))["config"])
        phase = "consumer"
        with patch.object(reuse, "CausalPreparationParser", lambda: parser):
            start = clock()
            prepared = reuse.prepare(
                original_prepare, native, archive, config, statistics=preparation_stats,
                screen_latitude_deg=offer.screen_center[0], screen_longitude_deg=offer.screen_center[1],
            )
            timings["consumer"] = elapsed(start)

    packed = _prepared_values(prepared)
    if packed["status"] != "inputs_prepared" or native_counts["fallback"] or parser.stats["fallback_calls"]:
        raise ValueError("Expected the exact charged named parser and consumer path")
    prepared_sha256 = prepared_digest(packed)
    witness = parsed_witness(parser)
    if prime:
        exact_refs = select_sources(refs, cutoff)
        prime["actual_ordered_refs"] = [ref.path.name for ref in exact_refs]
        prime["actual_body_overlap"] = len(set(prime["digests"]) & {ref.sha256 for ref in exact_refs})
    save(output, dict(
        mode=mode, host=host, frozen_spec_sha256=SPEC_PIN, archive_digest=archive_digest,
        manifest_path=str(manifest_path), manifest_digest=manifest_digest,
        native_digest=NATIVE_PIN, offer_digest=request["offer_sha256"], actual_cutoff=cutoff,
        timings=timings, prime=prime, reads=reads, calls=calls, native_prime=prime_native,
        native_consumer={key: count - prime_native[key] for key, count in native_counts.items()},
        parser_before=parser_before, parser_after=parser.stats, graph=graph_counts,
        catalogue_costs=catalogue_counts, prepared_sha256=prepared_sha256, witness=witness,
        metadata=packed["sky"]["metadata"], phase_history_sources=packed["phase_history"]["sources"],
        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    ))


def pair(output):
    output.mkdir()
    rows = {}
    for mode in ("ordinary", "primed"):
        path = output / f"{mode}.json"
        subprocess.run([sys.executable, "-BPs", __file__, str(path), "--worker", mode],
                       check=True, timeout=45)
        rows[mode] = json.loads(path.read_bytes())
    ordinary, primed = (rows[mode] for mode in ("ordinary", "primed"))
    keys = ("prepared_sha256", "witness", "metadata", "phase_history_sources", "actual_cutoff")
    equality = {key: ordinary[key] == primed[key] for key in keys}
    equality["ordinary_archive_reads"] = ordinary["reads"]["consumer_refs"] == primed["reads"]["consumer_refs"]
    result = dict(case="DS30-0008", order=list(rows), runs=rows, equality=equality,
                  driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                  request_sha256=REQUEST_PIN, input_boundary="saved detections and original manifest metadata")
    save(output / "pair.json", result)
    if not all(equality.values()):
        raise ValueError("Priming changed the exact prepared input or original read sequence")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    cli.add_argument("--worker", choices=("ordinary", "primed"))
    args = cli.parse_args()
    if args.worker:
        worker(args.worker, args.output)
    else:
        pair(args.output)
