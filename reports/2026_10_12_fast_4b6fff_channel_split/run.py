"""Replay channel subsets through the installed association/position public input port."""
import argparse
from collections import Counter
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import time
from unittest.mock import patch

from leo.cli import regional_position
from leo.contracts.digests import canonical_digest, sha256_digest
from leo.storage.regional_position_v3 import B7Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("case", choices=("ch1-4", "ch5-8", "ch1-8"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    adapter_path = Path("/opt/leo-fast-auto/20261011-r3/bin/fast_scan_standard_pipeline.py")
    spec = importlib.util.spec_from_file_location("installed_adapter", adapter_path)
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    payload = (root / "input/tracking.json").read_bytes()
    original = adapter.load_tracking_input(json.loads(payload))
    channels = {"ch1-4": range(1, 5), "ch5-8": range(5, 9), "ch1-8": range(1, 9)}[args.case]
    probes = tuple(p for p in original.probes if p.channel in channels)
    binding = canonical_digest({"parent_input": original.input_manifest_sha256,
                                "parent_analysis": original.analysis_manifest_sha256,
                                "channels": list(channels), "policy": "channel-subset-v1"})
    source = original if args.case == "ch1-8" else replace(
        original, probes=probes, input_manifest_sha256=binding)

    class InputPort:
        def __init__(self, _root):
            pass

        def load(self, session_id):
            assert session_id == source.session_id
            return source

        def close(self):
            pass

    output = root / args.case
    output.mkdir(exist_ok=True)
    receipt = {"case": args.case, "channels": list(channels),
               "parent_input_sha256": original.input_manifest_sha256,
               "export_sha256": sha256_digest(payload), "subset_binding": binding,
               "probe_counts": dict(Counter(p.channel for p in probes)),
               "receiver_counts": dict(Counter(p.receiver_id for p in probes)),
               "adapter": str(adapter_path), "engine": regional_position.__file__,
               "slice_seconds": 500, "maximum_slices": 3,
               "scope": "Fresh calibration, satellite association and regional position per channel subset; saved GLRT unchanged."}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    started = time.monotonic()
    with patch.object(regional_position, "ScannerTrackingInputStore", InputPort):
        for index in range(3):
            result = regional_position.run_regional_position_analysis(
                output, Path("/var/lib/leo/tle"), source.session_id, maximum_seconds=500)
            print(json.dumps({"case": args.case, "slice": index + 1,
                              "elapsed_s": time.monotonic() - started, **result}), flush=True)
            if result["state"] == "complete":
                break
    receipt.update(result=result, elapsed_s=time.monotonic() - started)
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if result["state"] != "complete":
        raise RuntimeError("Bounded replay did not complete")
    document = B7Store(output).status(source.session_id).manifest.document
    (output / "regional.json").write_text(document.model_dump_json(indent=2) + "\n")


if __name__ == "__main__":
    main()
