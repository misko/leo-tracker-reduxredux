"""Build the exact single-core Gauss receiver from its qualified C sources."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def build(output):
    source = Path(__file__).resolve().parent
    recipe = json.loads((source / "build.json").read_bytes())
    for name, expected in recipe["source_digests"].items():
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Source digest mismatch for {name}")
    with tempfile.TemporaryDirectory(dir=output.parent) as scratch:
        binary = Path(scratch).resolve() / "receiver.so"
        subprocess.run([recipe["cc"], *recipe["args"], "-o", binary], cwd=source, check=True)
        if hashlib.sha256(binary.read_bytes()).hexdigest() != recipe["rebuild_sha256"]:
            raise ValueError("Built receiver differs from the qualified Gauss binary")
        os.replace(binary, output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    build(parser.parse_args().output)
