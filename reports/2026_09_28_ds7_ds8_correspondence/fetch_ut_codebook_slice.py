"""Bounded range extraction of a narrow published-symbol slice, not raw IQ."""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports/2026_09_27_ds7_header"))
from fetch_ut_reference import URL, Remote  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-bin", type=int, choices=[100, 200], required=True)
    args = parser.parse_args()
    out = Path(__file__).parent / "local/ut-codebook"
    out.mkdir(exist_ok=True)
    remote = Remote()
    bins = np.arange(args.start_bin, args.start_bin + 4)
    with h5py.File(remote, "r") as source:
        raw = source["yDataDec"][:, :, bins]
    symbols = raw["real"] + 1j * raw["imag"]
    path = out / f"bins-{args.start_bin}.npz"
    np.savez_compressed(path, symbols=symbols, bins=bins)
    metadata = dict(
        url=URL,
        etag=remote.etag,
        fetched_bytes=remote.total,
        elapsed_s=time.monotonic() - remote.started,
        shape=list(symbols.shape),
        output_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        limitation="Published hard constellation symbols, not raw IQ or FEC bits",
    )
    path.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata), flush=True)


if __name__ == "__main__":
    main()
