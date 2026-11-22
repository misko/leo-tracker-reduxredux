"""Time metadata and a saved complete detection handoff without reading any I/Q."""

import argparse
import json
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns

from leo.contracts.digests import canonical_digest, sha256_digest
from leo.storage.fast_scan import FastScanStore, immutable_json
from tools.algo08_scan import PINS


def timed(action):
    elapsed, cpu = perf_counter_ns(), process_time_ns()
    value = action()
    return value, dict(cpu_s=(process_time_ns() - cpu) / 1e9, wall_s=(perf_counter_ns() - elapsed) / 1e9)


def measure(recording, detections, terminal, library, assets, pin):
    doc_bytes = detections.stat().st_size
    if not 0 < doc_bytes <= 16 * 1024**2:
        raise ValueError("detection receipt is outside the bounded comparison")
    expected = json.loads(terminal.read_bytes())
    files = {name: (assets / name, digest) for name, digest in PINS.items()}
    files["cancellation-factors.so"] = library, pin

    def verify_assets():
        for path, digest in files.values():
            if sha256_digest(path.read_bytes()) != "sha256:" + digest:
                raise ValueError(f"unqualified experiment asset {path.name}")

    return_rows = []
    with TemporaryDirectory(prefix="algo08-detection-boundary-") as directory:
        for repeat in range(7):
            store = FastScanStore(Path(directory) / str(repeat))
            _, asset_check = timed(verify_assets)
            binding, inv = timed(lambda: store.inventory(recording, verify_windows=False))
            session, manifest, inventory = binding
            payload, read = timed(detections.read_bytes)
            native, parse = timed(lambda: json.loads(payload))
            bound = native["source"]
            if session != expected["session_id"] or len(payload) != doc_bytes or (
                    manifest != bound["input_manifest_sha256"] or bound["session_id"] != session or
                    native["provenance"]["detector_sha256"] != "sha256:" + pin or
                    sha256_digest(payload) != expected["native_sha256"]):
                raise ValueError("recording, detector or canonical output differs from the paired publication")
            got, check = timed(lambda: canonical_digest([
                "cancellation", bound["raw_recording_authority_digest"], pin, bound["probes"],
            ]))
            if got != bound["analysis_manifest_sha256"]:
                raise ValueError("saved factors disagree with the acquisition digest")
            destination = Path(directory) / f"{repeat}.json"
            _, seal = timed(lambda: immutable_json(destination, native))
            _, inventory_seal = timed(lambda: store.publish_inventory(session, inventory))
            if destination.read_bytes() != payload:
                raise ValueError("immutable seal changed saved detection bytes")
            return_rows.append(dict(asset_validation=asset_check, segment_inventory=inv, detections_read=read,
                                    detections_decode=parse, probe_digest_check=check, immutable_seal=seal,
                                    inventory_seal=inventory_seal))
    return dict(bytes=doc_bytes, scheduled_visits=inventory["window_count"], segments=len(inventory["segments"]),
                ordered_lanes=len(bound["probes"]), native_sha256=expected["native_sha256"],
                output_bytes_matched=True, repeats=return_rows,
                median_cpu_s={name: median(row[name]["cpu_s"] for row in return_rows)
                              for name in return_rows[0]})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("detections", type=Path)
    parser.add_argument("terminal", type=Path)
    parser.add_argument("library", type=Path)
    parser.add_argument("assets", type=Path)
    parser.add_argument("binary_sha256")
    args = parser.parse_args()
    print(json.dumps(measure(args.recording, args.detections, args.terminal, args.library, args.assets,
                             args.binary_sha256), indent=2))
