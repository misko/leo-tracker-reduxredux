"""Run original and tiled full coarse grids and require byte parity."""

import argparse
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("tiled", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as name:
        original = Path(name) / "original.bin"
        tiled = Path(name) / "tiled.bin"
        subprocess.run([args.original, original], check=True)
        subprocess.run([args.tiled, tiled], check=True)
        assert original.read_bytes() == tiled.read_bytes()
    print("all-rate full coarse grids are bit exact")


if __name__ == "__main__":
    main()
