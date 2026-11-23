"""Derive a private ALGO08v3 payload with the pinned retimed native receiver."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy
from shutil import copytree
from tempfile import TemporaryDirectory


DETECTOR_SHA256 = "7ac6de98302ce65c52fdad2f630094e14ab4c503999ba9f3695be2c4403a51b1"


def prepare(detector):
    bounds = runpy.run_path(str(Path(__file__).with_name("run-bounds")))
    baseline, target = bounds["BASELINE"], bounds["BOUNDS_PAYLOAD"]
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    if sha256(baseline.read_bytes()).hexdigest() != bounds["BASELINE_SHA256"]:
        raise ValueError("The installed ALGO08v3 launcher changed")
    release = baseline.parent / "payload"
    installed = runpy.run_path(str(baseline))
    installed["checked_spec"](release, bounds["FROZEN_SPEC"])
    binary = detector.read_bytes()
    if sha256(binary).hexdigest() != DETECTOR_SHA256:
        raise ValueError("The benchmark receiver differs from the selected native build")

    with TemporaryDirectory(dir=target.parent) as scratch:
        payload = Path(scratch) / "payload"
        copytree(release, payload)
        (payload / "receiver.so").write_bytes(binary)
        spec_path = payload / "spec.json"
        spec = json.loads(spec_path.read_bytes())
        spec["detector_sha256"] = spec["sources"]["receiver.so"] = DETECTOR_SHA256
        spec_path.write_text(json.dumps(spec, sort_keys=True, separators=(",", ":"),
                                        allow_nan=False, ensure_ascii=False))
        installed["checked_spec"](payload, bounds["BOUNDS_SPEC"])
        for path in payload.rglob("*"):
            path.chmod(path.stat().st_mode & ~0o222)
        payload.rename(target)
        target.chmod(target.stat().st_mode & ~0o222)
    print(target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("detector", type=Path)
    prepare(parser.parse_args().detector)
