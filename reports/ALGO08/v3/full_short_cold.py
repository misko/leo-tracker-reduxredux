"""Fresh reversed cold pairs through immutable signed prefix detections."""

import argparse
from contextlib import closing, contextmanager
import ctypes as ct
from dataclasses import asdict
from hashlib import sha256
from importlib import import_module
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from . import mixed_aperture_receiver, sparse_cold_input as cold
from .mixed_aperture_receiver import FULL_RULE, PILOT_SHA, MixedApertureDetector
from .scout_readout_trial import check_machine


HERE = Path(__file__).resolve().parent
SHORT_SHA = "06570a53032c770d99cc9678b8660e1bb502b71f30fc47c8b1a4a8e31bc19ba9"
ORDERS = (("stock", "full-short"), ("full-short", "stock"))
MEASURED = HERE / "measurements"
PRIOR_RECEIPT_SHA = "9b08991d255d82217e7447dd87c211aaf08221f652381a785c2c6e5a0a990847"


def freeze(path, data):
    with path.open("x") as stream:
        json.dump(data, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def recipe(installed):
    return dict(installed_sha256=installed, shortened_sha256=SHORT_SHA,
                callback_sha256=sha256(Path(mixed_aperture_receiver.__file__).read_bytes()).hexdigest(),
                rule=list(FULL_RULE), streams=["edge", "channel", "actual_rf_hz"], aperture_samples=[200000, 120000],
                selection="maximum verified fractional margin, lower native rank on tie; verified rank zero at nonanchors")


def scope(arm, assets, short_binary, spec, request, output):
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import FastSegmentSource, immutable_json
    from tools import algo08_scan
    from tools.pipeline_eval.qualification import blind_compact_run as blind
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes

    buffer = cold.frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    advice = cold.frozen_function(spec, "receiver_member_lookahead.py", "compressed_member_lookahead")
    installed_sha = spec["detector_sha256"]
    base = algo08_scan.detector
    stock_native = blind.Native
    mix = None if arm == "stock" else MixedApertureDetector(short_binary, SHORT_SHA, full_coverage=True)
    detector_pin = installed_sha if mix is None else canonical_digest(recipe(installed_sha))[7:]
    digests, callback_clocks = [], []
    clocks = dict(calls=0, cpu_ns=0, wall_ns=0)

    class Bounded(FastSegmentSource):
        def __init__(self, entry):
            super().__init__(entry, stop_sequence=cold.WINDOWS)

        def windows(self):
            with closing(super().windows()) as windows:
                for window in windows:
                    digests.append(window.iq_sha256)
                    yield window

    class TimedNative(stock_native):
        def __init__(self, path, asset):
            super().__init__(path, asset)
            native_call = self.lib.cancellation_factors
            native_call.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, ct.c_double, ct.POINTER(blind.Factor)]
            native_call.restype = ct.c_int

            def timed(*args):
                begin = process_time_ns(), perf_counter_ns()
                result = native_call(*args)
                cpu_ns, wall_ns = process_time_ns()-begin[0], perf_counter_ns()-begin[1]
                clocks["calls"] += 1
                clocks["cpu_ns"] += cpu_ns
                clocks["wall_ns"] += wall_ns
                return result

            self.lib.cancellation_factors = timed

    @contextmanager
    def observe(*args, **kwargs):
        selected = base if mix is None else mix.detector
        with selected(*args, **kwargs) as receive:
            def visit(window):
                start = process_time_ns(), perf_counter_ns()
                rows = receive(window)
                callback_clocks.append((process_time_ns()-start[0], perf_counter_ns()-start[1]))
                return rows

            yield visit

    before_io = cold.io_snapshot()
    before = resource.getrusage(resource.RUSAGE_SELF)
    cpu, wall = process_time_ns(), perf_counter_ns()
    with (buffer(), paired_decoded_hashes(cold.PAYLOAD / "paired-sha256.so"), advice() as hints,
          patch.object(algo08_scan, "FastSegmentSource", Bounded),
          patch.object(algo08_scan, "detector", observe), patch.object(blind, "Native", TimedNative if mix is None else stock_native),
          patch.dict(algo08_scan.PINS, {"cancellation-factors.so": detector_pin})):
        document = algo08_scan.acquire(request["session"], request["inventory_digest"],
                                      dict(segments=[request["entry"]], window_count=cold.WINDOWS), assets)
    acquire_cpu_ns, acquire_wall_ns = process_time_ns()-cpu, perf_counter_ns()-wall
    immutable_json(output, document)
    content = output.read_bytes()
    document = json.loads(content)
    source = document["source"]
    raw = canonical_digest([request["inventory_digest"], digests])
    detector_manifest = canonical_digest(["cancellation", raw, detector_pin, source["probes"]])
    if (source["raw_recording_authority_digest"] != raw or source["analysis_manifest_sha256"] != detector_manifest
            or document["provenance"]["detector_sha256"] != "sha256:" + detector_pin
            or len(digests) != cold.WINDOWS or len(callback_clocks) != cold.WINDOWS
            or len(source["probes"]) != 2 * cold.WINDOWS or document["provenance"]["invalid_capture"]):
        raise ValueError("Sealed detection source, authority or qualified visit count differs")
    digest = sha256(content).hexdigest()
    cpu_ns, wall_ns = process_time_ns()-cpu, perf_counter_ns()-wall
    after = resource.getrusage(resource.RUSAGE_SELF)
    after_io = cold.io_snapshot()
    callback_cpu, callback_wall = map(sum, zip(*callback_clocks, strict=True))
    native = (dict(native_calls={"full": clocks["calls"]}, native_cpu_ns={"full": clocks["cpu_ns"]},
                   native_wall_ns={"full": clocks["wall_ns"]}) if mix is None else mix.receipt())
    if sum(native["native_calls"].values()) != 2 * cold.WINDOWS:
        raise ValueError("Every admitted stereo lane must issue exactly one native call")
    return dict(arm=arm, detector_pin=detector_pin, visits=len(callback_clocks), raw_authority=raw,
                sealed_detection_sha256=digest, decoded_iq_hashes=digests, overlap=asdict(hints), native=native,
                cpu_ns=cpu_ns, wall_ns=wall_ns, acquire_cpu_ns=acquire_cpu_ns, acquire_wall_ns=acquire_wall_ns,
                callback_cpu_ns=callback_cpu, callback_wall_ns=callback_wall,
                resource_input_blocks=after.ru_inblock-before.ru_inblock,
                resource_output_blocks=after.ru_oublock-before.ru_oublock,
                process_io_delta={key: after_io[key]-value for key, value in before_io.items()})


def worker(arm, request_path, short_binary, output):
    machine = check_machine()
    spec = json.loads(cold.verified(cold.PAYLOAD / "spec.json", cold.SPEC_SHA))
    request = json.loads(request_path.read_bytes())
    row = scope(arm, request_path.parent / "assets", short_binary, spec, request, output)
    freeze(output.with_suffix(".receipt.json"), dict(row, machine=machine))


def run(parent, short_binary, output):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification.cache_residency import load_query, pages
    from tools.pipeline_eval.variants.experimental.paired_sha256 import PairedSha256

    host = check_machine()
    parent = parent.resolve(strict=True)
    if Path("/srv/bulk/leo-dev") not in (parent, *parent.parents):
        raise ValueError("Expected the existing local research staging area")
    filesystem = subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", parent], text=True).strip()
    if filesystem != "xfs":
        raise ValueError("Expected local XFS")
    spec = json.loads(cold.verified(cold.PAYLOAD / "spec.json", cold.SPEC_SHA))
    for name, expected in cold.RUNTIME.items():
        cold.verified(Path(import_module(name).__file__), expected)
    receiver = cold.PAYLOAD / "receiver.so"
    cold.verified(receiver, spec["detector_sha256"])
    cold.verified(short_binary, SHORT_SHA)
    hasher = cold.PAYLOAD / "paired-sha256.so"
    cold.verified(hasher, spec["paired_sha256"]["sha256"])
    if not PairedSha256(hasher).hardware:
        raise ValueError("Expected the installed hardware paired SHA-256")
    cold.verified(cold.CACHE_LIBRARY, cold.CACHE_SHA)
    query = load_query(cold.CACHE_LIBRARY)
    native_path, = (cold.ARCHIVE / "fast-scan-automatic-work").glob("*/detections.json")
    native = json.loads(cold.verified(native_path, cold.ARCHIVED_DETECTION_SHA))
    session = native["source"]["session_id"]
    inventory = json.loads((cold.ARCHIVE / "fast-scan-inputs" / f"{session}.json").read_bytes())
    inventory_digest = canonical_digest(inventory)
    original = inventory["segments"][0]
    binding = json.loads(cold.verified(cold.BINDING, cold.BINDING_SHA))["case"]["recording"]["segments"][0]
    if (inventory_digest != native["source"]["input_manifest_sha256"]
            or Path(original["path"]) / "manifest.json" != Path("/srv/bulk") / binding["path"]
            or original["manifest_digest"] != "sha256:" + binding["sha256"]):
        raise ValueError("The copied authority differs from the original signed input")
    output.mkdir()
    with TemporaryDirectory(dir=parent, prefix="leo-private-full-short-cold-") as tmp:
        private = Path(tmp)
        assets = private / "assets"
        assets.mkdir()
        (assets / "cancellation-factors.so").symlink_to(receiver)
        pilot = cold.RELEASE / "assets/lower.f32"
        cold.verified(pilot, PILOT_SHA["lower"])
        (assets / "lower.f32").symlink_to(pilot)
        copy_cpu, copy_wall = process_time_ns(), perf_counter_ns()
        entry, chunks, members = cold.copy_prefix(private, original)
        staging = dict(coordinator_cpu_ns=process_time_ns()-copy_cpu, wall_ns=perf_counter_ns()-copy_wall)
        identities = [cold.private_identity(path, private) for path in members]
        payload = sum(chunk.compressed_bytes for chunk in chunks)
        expected_pages = [pages(chunk.compressed_bytes, os.sysconf("SC_PAGE_SIZE")) for chunk in chunks]
        request = private / "request.json"
        freeze(request, dict(entry=entry, session=session, inventory_digest=inventory_digest))
        pairs, common_metadata = [], None
        for index, order in enumerate(ORDERS):
            pair = []
            for arm in order:
                copy_cpu, copy_wall = process_time_ns(), perf_counter_ns()
                start_cache = [cold.cache_pages(path, private, info, query, cold=True)
                               for path, info in zip(members, identities, strict=True)]
                if any(start_cache):
                    raise ValueError("Cold-establishment left payload cache pages resident")
                eviction = dict(coordinator_cpu_ns=process_time_ns()-copy_cpu, wall_ns=perf_counter_ns()-copy_wall)
                prefix = private / f"{index}-{arm}.json"
                outer = perf_counter_ns()
                subprocess.run([sys.executable, "-P", "-m", __spec__.name, "worker", arm, request, short_binary, prefix],
                               check=True)
                dispatch_ns = perf_counter_ns()-outer
                end_cache = [cold.cache_pages(path, private, info, query, cold=False)
                             for path, info in zip(members, identities, strict=True)]
                row = json.loads(prefix.with_suffix(".receipt.json").read_bytes())
                content = cold.verified(prefix, row["sealed_detection_sha256"])
                document = json.loads(content)
                source = document["source"]
                probes = source["probes"]
                metadata = [dict(probe, candidates=[]) for probe in probes]
                if (common_metadata is not None and metadata != common_metadata
                        or document["delivery_clocks"] != native["delivery_clocks"][:cold.WINDOWS]
                        or document["clock_anchor"] != native["clock_anchor"]
                        or arm == "stock" and probes != cold.expected_prefix(native, cold.WINDOWS)):
                    raise ValueError("Fresh ingress or installed output differs from the original prefix")
                common_metadata = metadata
                hints = row["overlap"]
                if (hints["submitted"], hints["submitted_bytes"]) != (cold.MEMBERS-1, 2 * 16*1024**2):
                    raise ValueError("The released path did not issue both capped hints")
                with (output / prefix.name).open("xb") as stream:
                    stream.write(content)
                row.update(start_cache_pages=start_cache, end_cache_pages=end_cache, eviction=eviction,
                           subprocess_wall_ns=dispatch_ns, omitted_subprocess_wall_ns=dispatch_ns-row["wall_ns"],
                           effective_compressed_MB_per_s=payload*1000/row["wall_ns"], detection_file=prefix.name,
                           selected=sum(bool(probe["candidates"]) for probe in probes))
                pair.append(row)
            pairs.append(pair)
        flat = [row for pair in pairs for row in pair]
        if any(row["decoded_iq_hashes"] != flat[0]["decoded_iq_hashes"] or row["raw_authority"] != flat[0]["raw_authority"]
               for row in flat):
            raise ValueError("Receiver arms did not decode identical signed waveforms")
        pins = {arm: {row["sealed_detection_sha256"] for row in flat if row["arm"] == arm} for arm in ORDERS[0]}
        if any(len(hash_set) != 1 for hash_set in pins.values()) or pins["stock"] == pins["full-short"]:
            raise ValueError("Expected reproducible within-arm evidence and distinct algorithm provenance")
    freeze(output / "acquisition.json", dict(machine=host, filesystem=filesystem, kernel=os.uname().release,
            orders=ORDERS, repeats=pairs, staged=staging, expected_pages=expected_pages, decoded_bytes=sum(
                chunk.uncompressed_bytes for chunk in chunks), compressed_bytes=payload, spec_sha256=cold.SPEC_SHA,
            reader_sha256=cold.RUNTIME, archived_stock_sha256=cold.ARCHIVED_DETECTION_SHA, inventory_sha256=inventory_digest,
            prior_same_slice_sha256=PRIOR_RECEIPT_SHA, research_recipe=recipe(spec["detector_sha256"]),
            verified_chunks=[chunk.model_dump(mode="json") for chunk in chunks]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    stage, child = (actions.add_parser(name) for name in ("run", "worker"))
    stage.add_argument("parent", type=Path)
    child.add_argument("arm", choices=ORDERS[0])
    child.add_argument("request_path", type=Path)
    for sub in (stage, child):
        for name in ("short_binary", "output"):
            sub.add_argument(name, type=lambda value: Path(value).resolve())
    args = vars(parser.parse_args())
    {"run": run, "worker": worker}[args.pop("action")](**args)
