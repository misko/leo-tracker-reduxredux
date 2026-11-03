"""Export a frozen Python PSD bank for the standalone C timing probe.

Binary order is a 24-byte little-endian header (magic ``PSD11V1\0``, uint32
nfft, uint32 bin count, float64 sample rate), followed by float64 CFO values,
then row-major log features and row-major square-root features.
"""

import argparse
import struct
from pathlib import Path

import numpy as np

from psd_proposal import load_complex128, make_bank


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rate_hz", type=float)
    parser.add_argument("template", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    bank = make_bank(load_complex128(args.template), args.rate_hz)
    with args.output.open("xb") as stream:
        stream.write(struct.pack("<8sIId", b"PSD11V1\0", bank["nfft"], 11, args.rate_hz))
        for key in ("cfo_bins_hz", "log_features", "sqrt_features"):
            np.asarray(bank[key], dtype="<f8", order="C").tofile(stream)


if __name__ == "__main__":
    main()
