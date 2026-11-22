"""Measure the normal ALGO08 acquisition caller on bounded sealed prefixes."""

import argparse
import cProfile
import json
import pstats
import resource
from collections import defaultdict
from contextlib import contextmanager, nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from leo.contracts.digests import canonical_digest
from leo.storage.fast_scan import FastSegmentSource, immutable_json

from tools import algo08_scan
from tools.pipeline_eval.qualification import blind_compact_run

from .receiver_benchmark import digest
from .receiver_ingress import compressed_input_buffer, decoded_chunk_buffer


class Timers:
    def __init__(self):
        self.data = defaultdict(lambda: [0, 0, 0])

    @contextmanager
    def span(self, stage):
        wall, cpu = perf_counter_ns(), process_time_ns()
        try:
            yield
        finally:
            calls = self.data[stage]
            calls[1] += process_time_ns() - cpu
            calls[2] += perf_counter_ns() - wall
            calls[0] += 1

    def receipt(self):
        return {name: dict(calls=calls, cpu_s=cpu / 1e9, wall_s=wall / 1e9)
                for name, (calls, cpu, wall) in self.data.items()}


class NativeFactors:
    def __init__(self, fn, timers):
        self.fn = fn
        self.timers = timers

    @property
    def argtypes(self):
        return self.fn.argtypes

    @argtypes.setter
    def argtypes(self, value):
        self.fn.argtypes = value

    @property
    def restype(self):
        return self.fn.restype

    @restype.setter
    def restype(self, value):
        self.fn.restype = value

    def __call__(self, *args):
        with self.timers.span("native_factors"):
            return self.fn(*args)


def prefix_entry(binding, root, limit):
    case = json.loads(binding.read_bytes())["case"]
    segment = case["recording"]["segments"][0]
    manifest = (root / segment["path"]).resolve(strict=True)
    entry = dict(path=str(manifest.parent), manifest_digest="sha256:" + segment["sha256"])
    return case["id"], case["session_id"], dict(segments=[entry], window_count=limit)


def evaluate(case, binary, assets, work, *, ingress):
    ident, session, inventory = case
    limit = inventory["window_count"]
    timers = Timers()
    builtin_profile = cProfile.Profile(timer=process_time_ns, timeunit=1e-9)
    bind_native = blind_compact_run.Native

    def native(binary_path, pilot):
        with timers.span("native_context"):
            context = bind_native(binary_path, pilot)
        context.lib.cancellation_factors = NativeFactors(context.lib.cancellation_factors, timers)
        return context

    @contextmanager
    def detector(method, edge, **kwargs):
        opened = blind_compact_run.detector(method, edge, **dict(kwargs, binary=binary))
        with timers.span("receiver_open"):
            detect = opened.__enter__()
        try:
            def inspect(window):
                with timers.span("receiver_adapter"):
                    return detect(window)

            yield inspect
        finally:
            with timers.span("receiver_close"):
                opened.__exit__(None, None, None)

    class Segment(FastSegmentSource):
        def __init__(self, entry):
            with timers.span("segment_header"):
                super().__init__(entry, stop_sequence=limit)

        def windows(self):
            chunk = self.reader.manifest.chunks[0]
            if ingress == "decoded":
                if chunk.window_count < limit:
                    raise ValueError("decoded buffering is bounded to one sealed chunk")
                buffers = decoded_chunk_buffer(chunk.uncompressed_bytes)
            elif ingress == "compressed":
                buffers = compressed_input_buffer()
            else:
                buffers = nullcontext()
            with buffers:
                iterator = super().windows()
                while True:
                    with timers.span("verified_reader"):
                        window = next(iterator, None)
                    if window is None:
                        return
                    yield window

    binary_sha = digest(binary.read_bytes())
    pin = {"cancellation-factors.so": binary_sha}
    identity = canonical_digest(["bounded-acquisition-profile", inventory])
    with patch.object(algo08_scan, "FastSegmentSource", Segment), \
            patch.object(algo08_scan, "detector", detector), \
            patch.object(blind_compact_run, "Native", native), patch.dict(algo08_scan.PINS, pin):
        with timers.span("acquire"):
            document = builtin_profile.runcall(algo08_scan.acquire, session, identity, inventory, assets)

    path = work / "detections.json"
    with timers.span("seal"):
        immutable_json(path, document)
    with timers.span("read_and_revalidate"):
        bound = json.loads(path.read_bytes())["source"]
        if bound["analysis_manifest_sha256"] != canonical_digest([
                "cancellation", bound["raw_recording_authority_digest"], binary_sha, bound["probes"]]):
            raise ValueError("saved factors disagree with acquisition receipt")
    rows = pstats.Stats(builtin_profile).stats
    profile = {}
    for (file, _, name), (_, count, own, cumulative, _) in rows.items():
        if file == "~" and any(token in name for token in
                              ("posix.read", "ZstdDecompressionReader", "_hashlib", "validate_json")):
            profile[name] = dict(calls=count, own_cpu_s=own, cumulative_cpu_s=cumulative)
    return dict(case=ident, authorized_visits=limit, processed=document["provenance"]["processed_windows"],
                factor_sha256=canonical_digest(bound["probes"]), binary_sha256=binary_sha,
                raw_sha256=bound["raw_recording_authority_digest"],
                ingress=ingress, peak_process_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                stages=timers.receipt(), profiled_builtins=profile)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("oracle", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("bindings", type=Path, nargs="+")
    parser.add_argument("--bulk", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--visits", type=int, default=40)
    parser.add_argument("--ingress", choices=["release", "compressed", "decoded"], default="release",
                        help="opt in to compressed-only or full decoded chunk buffering in the candidate")
    args = parser.parse_args()
    if not 1 <= len(args.bindings) <= 2 or not 1 <= args.visits <= 64:
        parser.error("profile at most the first 64 visits of two sealed recordings")
    pairs = []
    for index, binding in enumerate(args.bindings):
        case = prefix_entry(binding, args.bulk, args.visits)
        bins = [(args.oracle, "release"), (args.candidate, args.ingress)]
        if index % 2:
            bins.reverse()
        pair = []
        for binary, ingress in bins:
            with TemporaryDirectory(prefix="algo08-acquisition-profile-") as work:
                pair.append(evaluate(case, binary, args.assets, Path(work), ingress=ingress))
        if pair[0]["factor_sha256"] != pair[1]["factor_sha256"] or pair[0]["raw_sha256"] != pair[1]["raw_sha256"]:
            raise ValueError("matched acquisition prefixes disagree")
        pairs.append(pair)
    print(json.dumps(pairs, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
