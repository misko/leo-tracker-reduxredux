"""Measure a serial descriptor, authenticated traversal and signed detector on the same private input."""

import argparse
from contextlib import closing, contextmanager, nullcontext
import gzip
from hashlib import sha256
from importlib import import_module
import json
import os
from pathlib import Path
import resource
import subprocess
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from . import full_short_cold as full, signed_ingress_reuse_trial as saved, sparse_cold_input as cold
from .mixed_aperture_receiver import MixedApertureDetector
from .signed_ingress_reuse import AcquisitionCosts, measured_ingress


HERE = Path(__file__).resolve().parent
MEMBERS, WINDOWS = 2, 128
ORDERS = (("read", "verify", "dsp"), ("dsp", "verify", "read"))
PRIOR_SHA = "2632873af2697761fff90fa846aae2cdba8278a5d99f75eeaa302d41cb234439"
ARCHIVED_DSP = Path("/var/tmp/leo-full-short-dense-DS30-0008/publication/fast-scan-automatic-work/"
                    "algo08-v2-3dce9426edd1831eade2003d69a00297/detections.json")
ARCHIVED_DSP_SHA = "ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85"


def kernel_counters():
    r = resource.getrusage(resource.RUSAGE_SELF)
    runtime, runqueue, slices = map(int, Path("/proc/self/schedstat").read_text().split())
    block_delay = int(Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()[39])
    return dict(cold.io_snapshot(), scheduler_cpu_ns=runtime, scheduler_runqueue_ns=runqueue, scheduler_slices=slices,
                block_delay_ticks=block_delay, input_blocks=r.ru_inblock, output_blocks=r.ru_oublock,
                minor_faults=r.ru_minflt, major_faults=r.ru_majflt,
                voluntary_switches=r.ru_nvcsw, involuntary_switches=r.ru_nivcsw)


def transfer_only(entry, chunks, expected_manifest, buffer, costs):
    from leo.storage.scanner import ScannerIqStore

    root = Path(entry["path"])
    # Use the same descriptor selection as the complete reader but no SHA or decoder.
    matched = [("manifest.json", expected_manifest)] + [
        (name, size) for c in chunks for name, size in ((c.index_relative_path, c.index_bytes),
                                                       (c.payload_relative_path, c.compressed_bytes))]
    seen = []
    with buffer():
        for name, size in matched:
            stage = "compressed_descriptor" if name.endswith(".zst") else "other_descriptors"
            block = costs.time(stage, ScannerIqStore._read_regular, root / cold.source_member_name(name), size)
            if len(block) != size:
                raise ValueError("Descriptor returned an incomplete original member")
            seen.append([name, len(block)])
            del block
    return dict(read_extents=seen)


def acquired(arm, request, assets, native_binary, spec, buffer, costs):
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import FastSegmentSource
    from tools import algo08_scan
    from tools.pipeline_eval.qualification.blind_compact_run import _probe
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes

    entry = request["entry"]
    digests = []

    class Bounded(FastSegmentSource):
        def __init__(self, original):
            super().__init__(original, stop_sequence=WINDOWS)

        def windows(self):
            with closing(super().windows()) as stream:
                for window in stream:
                    digests.append(window.iq_sha256)
                    yield window

    saved_dsp = arm == "dsp"
    detector = MixedApertureDetector(native_binary, full.SHORT_SHA, full_coverage=True) if saved_dsp else None
    provenance = canonical_digest(full.recipe(spec["detector_sha256"]) if saved_dsp else ["verify-empty"])

    @contextmanager
    def receive(*args, **kwargs):
        selected = detector.detector(*args, **kwargs) if saved_dsp else nullcontext(
            lambda window: [_probe(window, lane, []) for lane in window.receiver_ids])
        with selected as scan:
            yield lambda window: costs.time("callback", scan, window)

    with (measured_ingress(buffer, costs), paired_decoded_hashes(cold.PAYLOAD / "paired-sha256.so"),
          patch.object(algo08_scan, "FastSegmentSource", Bounded), patch.object(algo08_scan, "detector", receive),
          patch.dict(algo08_scan.PINS, {"cancellation-factors.so": provenance[7:]})):
        doc = algo08_scan.acquire(request["session"], request["inventory_digest"],
                                  dict(segments=[entry], window_count=WINDOWS), assets)
    return dict(doc=doc, native=detector.receipt() if saved_dsp else None, decoded_iq_hashes=digests)


def verify_result(arm, row, expected, request, chunks):
    from leo.contracts.digests import canonical_digest

    raw = row.pop("doc")
    source = raw["source"]
    wanted_authority = canonical_digest([request["inventory_digest"], expected["iq"]])
    spans = row["work"]
    verified_members = [[name, size, digest] for c in chunks for name, size, digest in (
        (c.index_relative_path, c.index_bytes, c.index_sha256),
        (c.payload_relative_path, c.compressed_bytes, c.compressed_sha256))]
    probes = source["probes"]
    metadata = [dict(probe, candidates=[]) for probe in probes]
    if (row["decoded_iq_hashes"] != expected["iq"] or source["raw_recording_authority_digest"] != wanted_authority
            or metadata != expected["metadata"] or raw["delivery_clocks"] != expected["clocks"]
            or raw["clock_anchor"] != expected["clock_anchor"] or raw["provenance"]["invalid_capture"]
            or raw["provenance"]["window_count"] != WINDOWS
            or spans["verified_members"] != verified_members or spans["calls"]["decoded_sha"] != WINDOWS+MEMBERS
            or spans["calls"]["zstd_read"] != WINDOWS+MEMBERS
            or spans["decoded_members"] != [c.uncompressed_sha256 for c in chunks]):
        raise ValueError("Original authenticated input, visit identity or decoded extent differs")
    if arm == "dsp":
        if probes != expected["probes"] or row["native"]["native_calls"] != {"full": 32, "short_primary": 224}:
            raise ValueError("Signed DSP rows or full/short schedule differs")
    elif probes != metadata or row["native"] is not None:
        raise ValueError("The verify-only path returned detector work")
    row.update(raw_authority=wanted_authority, metadata_sha256=canonical_digest(metadata),
               probe_sha256=canonical_digest(probes), factors=sum(len(p["candidates"]) for p in probes),
               probes=len(probes), provenance=raw["provenance"])


def recover_stage(root, source):
    from leo.contracts.digests import canonical_digest
    from leo.contracts.multirate_window_recording import ShortWindowManifestV2

    binding = json.loads(cold.verified(cold.BINDING, cold.BINDING_SHA))["case"]["recording"]["segments"][0]
    session = source["session_id"]
    inventory = json.loads((cold.ARCHIVE / "fast-scan-inputs" / f"{session}.json").read_bytes())
    entry = inventory["segments"][0]
    inventory_pin = canonical_digest(inventory)
    origin = (Path("/srv/bulk") / binding["path"]).parent
    if (inventory_pin != source["input_manifest_sha256"] or Path(entry["path"]) != origin
            or binding["sha256"] != cold.MANIFEST_SHA or entry["manifest_digest"] != "sha256:"+cold.MANIFEST_SHA):
        raise ValueError("Recovery input differs from the frozen authority")
    segment = root / origin.name
    manifest = ShortWindowManifestV2.model_validate_json(cold.verified(segment / "manifest.json", cold.MANIFEST_SHA))
    chunks = tuple(manifest.chunks[:MEMBERS])
    payloads = tuple(segment / cold.source_member_name(c.payload_relative_path) for c in chunks)
    for chunk in chunks:
        for name, size in ((chunk.payload_relative_path, chunk.compressed_bytes), (chunk.index_relative_path, chunk.index_bytes)):
            if cold.private_identity(segment / cold.source_member_name(name), root)[2] != size:
                raise ValueError("The pre-existing private fixture is incomplete")
    request = root / "recovered-request.json"
    full.freeze(request, dict(entry=dict(entry, path=str(segment)), session=session, inventory_digest=inventory_pin))
    return request, chunks, payloads, dict(initial_outer_limit_s=75, initial_arms=0, additional_staging_bytes=0), inventory_pin


def run(parent, short_binary, output, private_copy=None):
    from tools.pipeline_eval.qualification.cache_residency import load_query, pages

    host = full.check_machine()
    parent = parent.resolve(strict=True)
    if (Path("/srv/bulk/leo-dev") not in (parent, *parent.parents)
            or subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", parent], text=True).strip() != "xfs"):
        raise ValueError("Use the authorized private XFS research staging area")
    spec = json.loads(cold.verified(cold.PAYLOAD / "spec.json", cold.SPEC_SHA))
    for name, expected in cold.RUNTIME.items():
        cold.verified(Path(import_module(name).__file__), expected)
    prior = json.loads(gzip.decompress(cold.verified(HERE / "measurements/dense-ingress-attribution.json.gz", PRIOR_SHA)))
    archived = json.loads(cold.verified(ARCHIVED_DSP, ARCHIVED_DSP_SHA))
    probes = [p for p in archived["source"]["probes"] if p["visit_index"] < WINDOWS]
    expected = dict(probes=probes, metadata=[dict(p, candidates=[]) for p in probes],
                    iq=prior["arms"][0]["decoded_iq_hashes"][:WINDOWS],
                    clocks=archived["delivery_clocks"][:WINDOWS], clock_anchor=archived["clock_anchor"])
    cold.verified(cold.CACHE_LIBRARY, cold.CACHE_SHA)
    cold.verified(short_binary, full.SHORT_SHA)
    cold.verified(cold.PAYLOAD / "receiver.so", spec["detector_sha256"])
    cold.verified(cold.RELEASE / "assets/lower.f32", full.PILOT_SHA["lower"])
    cold.verified(cold.PAYLOAD / "paired-sha256.so", spec["paired_sha256"]["sha256"])
    query = load_query(cold.CACHE_LIBRARY)
    buffer = cold.frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    output.mkdir()
    if private_copy is not None:
        private_copy = private_copy.resolve(strict=True)
        if private_copy.parent != parent or not private_copy.name.startswith("leo-physical-stage-envelope-"):
            raise ValueError("Recovery accepts only this trial's original private copy")
    staging_scope = (TemporaryDirectory(dir=parent, prefix="leo-physical-stage-envelope-") if private_copy is None
                     else nullcontext(private_copy))
    with staging_scope as tmp:
        root = Path(tmp)
        if private_copy is None:
            before = resource.getrusage(resource.RUSAGE_CHILDREN)
            with patch.object(cold, "MEMBERS", MEMBERS):
                request_path, chunks, payloads, staging, inventory = saved.stage(root, short_binary)
            after = resource.getrusage(resource.RUSAGE_CHILDREN)
            staging.update(child_cpu_s=(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime),
                           child_input_blocks=after.ru_inblock-before.ru_inblock,
                           child_output_blocks=after.ru_oublock-before.ru_oublock)
        else:
            request_path, chunks, payloads, staging, inventory = recover_stage(root, archived["source"])
        request = json.loads(request_path.read_bytes())
        models = [c.model_dump(mode="json") for c in chunks]
        if (models != prior["verified_chunks"][:MEMBERS] or inventory != prior["inventory"]
                or inventory != archived["source"]["input_manifest_sha256"]):
            raise ValueError("Prior input authority and staged members differ")
        segment = Path(request["entry"]["path"])
        indexes = tuple(segment / c.index_relative_path for c in chunks)
        ids = {p: cold.private_identity(p, root) for p in (*payloads, *indexes)}
        page_size = os.sysconf("SC_PAGE_SIZE")

        def cache(paths, *, evict=False):
            return [cold.cache_pages(p, root, ids[p], query, cold=evict) for p in paths]

        expected_payload = [pages(c.compressed_bytes, page_size) for c in chunks]
        expected_index = [pages(c.index_bytes, page_size) for c in chunks]
        nominal = sum(c.compressed_bytes for c in chunks)
        metadata_bytes = (segment / "manifest.json").stat().st_size
        rows = []
        for i, order in enumerate(ORDERS):
            for arm in order:
                before_pages, before_index = cache(payloads, evict=True), cache(indexes)
                if any(before_pages) or before_index != expected_index:
                    raise ValueError("The private file cache admission differs from the protocol")
                pressure = Path("/proc/pressure/io").read_text().splitlines()
                before = kernel_counters()
                begin_cpu, begin = process_time_ns(), perf_counter_ns()
                costs = AcquisitionCosts()
                if arm == "read":
                    row = transfer_only(request["entry"], chunks, metadata_bytes, buffer, costs)
                else:
                    row = acquired(arm, request, root / "assets", short_binary, spec, buffer, costs)
                elapsed, cpu = perf_counter_ns()-begin, process_time_ns()-begin_cpu
                after = kernel_counters()
                row.update(order=i+1, arm=arm, elapsed_ns=elapsed, cpu_ns=cpu, work=costs.receipt(),
                           kernel={key: after[key]-value for key, value in before.items()},
                           before_payload_pages=before_pages, after_payload_pages=cache(payloads),
                           before_index_pages=before_index, after_index_pages=cache(indexes),
                           io_pressure_before=pressure, io_pressure_after=Path("/proc/pressure/io").read_text().splitlines())
                if arm != "read":
                    verify_result(arm, row, expected, request, chunks)
                full.freeze(output / f"{i+1}-{arm}.json", row)
                rows.append(row)
        full.freeze(output / "envelope.json", dict(machine=host, arms=rows, orders=ORDERS, staging=staging,
                    chunks=models, inventory=inventory, manifest_bytes=metadata_bytes, payload_pages=expected_payload,
                    index_pages=expected_index, nominal_compressed_bytes_per_arm=nominal, block_tick_hz=os.sysconf("SC_CLK_TCK"),
                    signed_dsp_sha256=ARCHIVED_DSP_SHA, dense_ingress_sha256=PRIOR_SHA, runtime=cold.RUNTIME,
                    specification_sha256=cold.SPEC_SHA, short_receiver_sha256=full.SHORT_SHA,
                    source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("parent", "short_binary", "output"):
        p.add_argument(name, type=Path)
    p.add_argument("--private-copy", type=Path)
    run(**vars(p.parse_args()))
