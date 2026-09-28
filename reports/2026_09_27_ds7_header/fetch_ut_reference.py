"""Bounded HTTP-range extraction of published UT decoded carrier symbols."""

import hashlib
import io
import json
import time
import urllib.request
from pathlib import Path

import h5py
import numpy as np

URL = (
    "https://rnl-data.ae.utexas.edu/datastore/supplementaryMaterial/"
    "qin-starlink-pilots/exemplar-frames-data/decodedExemplarFrames_20251019T2214.mat"
)


class Remote(io.RawIOBase):
    def __init__(self):
        self.position = 0
        self.total = 0
        self.started = time.monotonic()
        with urllib.request.urlopen(urllib.request.Request(URL, method="HEAD"), timeout=10) as r:
            self.size = int(r.headers["Content-Length"])
            self.etag = r.headers.get("ETag")

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        self.position = offset + (self.position if whence == 1 else self.size if whence == 2 else 0)
        return self.position

    def readinto(self, buffer):
        n = len(buffer)
        if n == 0:
            return 0
        if self.total + n > 16 * 1024**2 or time.monotonic() - self.started > 110:
            raise OSError("Reference extraction exceeded its byte/time budget")
        headers = {"Range": f"bytes={self.position}-{self.position + n - 1}"}
        if self.etag:
            headers["If-Match"] = self.etag
        with urllib.request.urlopen(urllib.request.Request(URL, headers=headers), timeout=10) as r:
            if r.status != 206:
                raise OSError("Server did not honor bounded range request")
            if self.etag and r.headers.get("ETag") != self.etag:
                raise OSError("Reference changed during extraction")
            data = r.read(n + 1)
            if len(data) != n:
                raise OSError("Unexpected range length")
        buffer[:] = data
        self.position += n
        self.total += n
        return n


def main():
    out = Path(__file__).parent / "local/ut-reference"
    out.mkdir(exist_ok=True)
    bins = np.r_[476:488, 496:508]
    remote = Remote()
    with h5py.File(remote, "r") as source:
        # One 13-frame HDF5 chunk group containing the paper's example frame 814.
        raw = source["yDataDec"][806:819, :, bins]
    symbols = raw["real"] + 1j * raw["imag"]
    path = out / "decoded-upper-806-818.npz"
    np.savez_compressed(path, symbols=symbols, bins=bins, zero_based_frames=np.arange(806, 819))
    metadata = dict(
        url=URL,
        etag=remote.etag,
        remote_size=remote.size,
        fetched_bytes=remote.total,
        elapsed_s=time.monotonic() - remote.started,
        output_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        shape=list(symbols.shape),
        dataset="yDataDec",
        indexing="Zero-based dataset frame indices 806..818; OFDM symbols 1..301; native FFT bins.",
        limitation="Published hard constellation decisions; "
        "not raw IQ or independently verified FEC bits.",
    )
    (out / "inventory.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
