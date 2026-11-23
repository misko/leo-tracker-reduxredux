"""Measure the signed reader cost left by a stereo DSP mask on a bounded prefix."""

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import resource
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import DENSE, configuration, inputs, machine, read, write


PREFIX = 128
PATHS = ("full", "fixed", "no-dsp")


def compare(publication, specification, native, inventory, archive, offer, mode, skipped):
    from leo.contracts.digests import canonical_digest, sha256_digest
    from leo.storage.fast_scan import FastSegmentSource, immutable_json
    from tools import algo08_scan
    from tools.pipeline_eval.qualification import blind_compact_run

    source = native["source"]
    before = [row for row in source["probes"] if row["visit_index"] < PREFIX]
    known_metadata = {r["visit_index"]: r for r in before if r["receiver_id"] == 0}
    plan = {v for v in skipped if v < PREFIX}
    if (canonical_digest(inventory) != source["input_manifest_sha256"]
            or inventory["segments"][0]["windows"] < PREFIX or (mode == "fixed" and not plan)):
        raise ValueError("The signed inventory does not bind the bounded prefix or its mask")
    segment = inventory["segments"][0]
    prefix_inventory = dict(segments=[segment], window_count=PREFIX)
    digests, detector_clocks, context, member_sizes = [], [], [], []
    continuation_type = blind_compact_run.Continuation

    class Segment(FastSegmentSource):
        def __init__(self, entry):
            super().__init__(entry, stop_sequence=PREFIX)
            first, second, *_ = self.reader.manifest.chunks
            if first.window_count + second.window_count != PREFIX:
                raise ValueError("The bounded traversal must process two complete members")
            member_sizes.extend(chunk.compressed_bytes for chunk in (first, second))

        def windows(self):
            for item in super().windows():
                digests.append(item.iq_sha256)
                yield item

    def continuation():
        instance = continuation_type()
        context.append(instance)
        return instance

    stock_detector = algo08_scan.detector

    @contextmanager
    def detector(*args, **kwargs):
        with stock_detector(*args, **kwargs) as stock:
            current, = context

            def visit(w):
                index = w.acquisition["global_visit"]
                reference = known_metadata[index]
                if (reference["edge"] != w.target["edge"] or reference["channel"] != w.target["channel"]
                        or reference["actual_rf_hz"] != (w.acquisition["actual_if_center_hz"] + w.target["lnb_lo_hz"])):
                    raise ValueError("The original schedule differs from the signed RF metadata")
                if mode == "no-dsp" or (mode == "fixed" and index in plan):
                    rows = [blind_compact_run._probe(w, lane, []) for lane in w.receiver_ids]
                    for row in rows:
                        current.select(row)
                    return rows
                cpu, wall = process_time(), perf_counter()
                rows = stock(w)
                detector_clocks.append((index, process_time() - cpu, perf_counter() - wall))
                return rows

            yield visit

    def analyze(_recording, root, assets, _archive, _region):
        for name, expected in algo08_scan.PINS.items():
            if sha256_digest((assets / name).read_bytes()) != "sha256:" + expected:
                raise ValueError(f"Unqualified ALGO08 asset {name}")
        start_usage = resource.getrusage(resource.RUSAGE_SELF)
        start_cpu, start_wall = process_time(), perf_counter()
        document = algo08_scan.acquire(source["session_id"], source["input_manifest_sha256"],
                                       prefix_inventory, assets)
        path = root / "detections.json"
        immutable_json(path, document)
        bound = read(path)["source"]
        raw = canonical_digest([source["input_manifest_sha256"], digests])
        if (len(digests) != PREFIX or bound["raw_recording_authority_digest"] != raw
                or bound["analysis_manifest_sha256"] != canonical_digest([
                    "cancellation", raw, specification["detector_sha256"], bound["probes"]])):
            raise ValueError("Prefix digest does not bind verified inputs and detections")
        cpu, wall = process_time() - start_cpu, perf_counter() - start_wall
        usage = resource.getrusage(resource.RUSAGE_SELF)
        rows = bound["probes"]
        if (mode == "full" and rows != before) or any(
            dict(left, candidates=[]) != dict(right, candidates=[])
            for left, right in zip(rows, before, strict=True)
        ):
            raise ValueError("Original prefix observations or opportunities changed")
        kept = [(left["candidates"], right["candidates"])
                for left, right in zip(before, rows, strict=True) if left["visit_index"] not in plan]
        changes = dict(lost=sum(bool(a) and not b for a, b in kept), gained=sum(not a and bool(b) for a, b in kept),
                       changed=sum(bool(a) and bool(b) and a != b for a, b in kept))
        return dict(mode=mode, cpu_s=cpu, elapsed_s=wall, input_blocks=usage.ru_inblock - start_usage.ru_inblock,
                    detector_cpu_s=sum(row[1] for row in detector_clocks),
                    detector_elapsed_s=sum(row[2] for row in detector_clocks),
                    eligible_detector_cpu_s=sum(row[1] for row in detector_clocks if row[0] in plan),
                    dsp_stereo_visits=len(detector_clocks), planned_skips=sorted(plan),
                    scheduled=PREFIX, admitted=len(rows)//2, selected=sum(len(r["candidates"]) for r in rows),
                    compressed_bytes=member_sizes, full_raw_authority=source["raw_recording_authority_digest"],
                    scoped_raw_digest=raw, window_receipts=canonical_digest(digests),
                    probe_sha256=canonical_digest(rows), kept_probe_changes=changes)

    with TemporaryDirectory() as directory:
        scratch = Path(directory)
        offer_path = scratch / "offer.json"
        offer_path.write_text(json.dumps(offer))
        root = scratch / "output"
        root.mkdir()
        args = SimpleNamespace(recording=Path(segment["path"]), bulk_root=root, archive=archive, region=offer_path)
        with (patch.object(algo08_scan, "analyze", analyze), patch.object(algo08_scan, "detector", detector),
              patch.object(algo08_scan, "FastSegmentSource", Segment),
              patch.object(blind_compact_run, "Continuation", continuation)):
            return publication.run(args, specification)


def trial(output):
    publication, specification = configuration()
    from aperture_mask import masked

    native, archive, offer, _, identity = inputs("DS30-0008")
    session = native["source"]["session_id"]
    inventory = read(DENSE.parent / "baseline" / "fast-scan-inputs" / f"{session}.json")
    _, mask = masked(native, "fixed")
    rotations = []
    for offset in range(len(PATHS)):
        order = PATHS[offset:] + PATHS[:offset]
        rows = [compare(publication, specification, native, inventory, archive, offer, mode, mask["dropped"])
                for mode in order]
        rotations.append(rows)
    for field in ("full_raw_authority", "scoped_raw_digest", "window_receipts", "compressed_bytes", "scheduled", "admitted"):
        if any(row[field] != rotations[0][0][field] for rows in rotations for row in rows):
            raise ValueError(f"Integrity retention changed between branches: {field}")
    write(output, dict(identity=identity, machine=machine(), rotations=rotations))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    trial(**vars(parser.parse_args()))
