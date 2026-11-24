"""Split a completed raw fix's wall clock at its original on-disk publication times."""

import argparse
from hashlib import sha256
import json
from math import isfinite
from os import fstat
from pathlib import Path


def product_clocks(root, seal_sha256, mode):
    seal_bytes = (root / "prediction-seal.json").read_bytes()
    if sha256(seal_bytes).hexdigest() != seal_sha256:
        raise ValueError("The run seal differs")
    entries = json.loads(seal_bytes)

    def read(key):
        path = root / key
        if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
            raise ValueError("Invalid sealed product path")
        with path.open("rb") as stream:
            data = stream.read()
            mtime_ns = fstat(stream.fileno()).st_mtime_ns
        if sha256(data).hexdigest() != entries[key]:
            raise ValueError(f"Product differs from seal: {key}")
        return json.loads(data), mtime_ns

    clock, _ = read(f"{mode}-clock.json")
    clock = clock["clock"]
    origin, elapsed = clock["started_unix_ns"], clock["elapsed_s"]
    if clock["exit_code"] != 0 or not isfinite(elapsed) or elapsed <= 0:
        raise ValueError("Expected a completed process clock")
    times, products = {}, {}
    for filename in ("detections.json", "terminal.json"):
        keys = [key for key in entries if key.startswith(f"{mode}/") and Path(key).name == filename]
        if len(keys) != 1:
            raise ValueError(f"Expected exactly one {filename} in the sealed mode")
        key = keys[0]
        document, mtime_ns = read(key)
        times[filename] = (mtime_ns - origin) / 1e9
        products[filename] = {"path": key, "sha256": entries[key], "mtime_ns": mtime_ns}
        if filename == "terminal.json" and (document["decision"] != "ok" or
                document["native_sha256"] != "sha256:" + products["detections.json"]["sha256"]):
            raise ValueError("Expected a fix bound to these detections")
    detection, terminal = times["detections.json"], times["terminal.json"]
    if not 0 <= detection <= terminal <= elapsed:
        raise ValueError("Product times fall outside the measured process order")
    return dict(seal_sha256=seal_sha256, mode=mode, started_unix_ns=origin, elapsed_s=elapsed,
                launch_to_detections_s=detection, detections_to_terminal_s=terminal - detection,
                terminal_to_exit_s=elapsed - terminal, products=products)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("seal_sha256")
    parser.add_argument("mode", choices=("stock", "candidate"))
    args = parser.parse_args()
    print(json.dumps(product_clocks(args.root, args.seal_sha256, args.mode), indent=2, allow_nan=False))
