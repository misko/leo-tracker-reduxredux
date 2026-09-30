"""Fetch bounded soft-decision carriers to audit mixed-symbol hard slicing."""

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
from fetch_full_reference import URL, Remote, decode_chunk

BASE = Path(__file__).resolve().parent


def main():
    out = BASE / "local/soft-transition-0-12.npz"
    if out.exists():
        raise FileExistsError("Keep existing cache; do not overwrite")
    bins = np.arange(400, 464)
    remote = Remote()
    with h5py.File(remote, "r") as source:
        data = source["yDataSoft"]
        assert data.shape == (1009, 301, 1024)
        assert data.chunks == (13, 301, 1)
        filters = data.id.get_create_plist()
        assert filters.get_nfilters() == 1 and filters.get_filter(0)[0] == 1
        dtype = data.dtype
        chunks = [data.id.get_chunk_info_by_coord((0, 0, int(b))) for b in bins]
        assert all(c.filter_mask == 0 and c.size > 0 for c in chunks)
        start = min(c.byte_offset for c in chunks)
        stop = max(c.byte_offset + c.size for c in chunks)
        if stop - start > 12 * 1024**2:
            raise ValueError("Soft chunk range exceeds download bound")
        remote.seek(start)
        blob = remote.read(stop - start)
    symbols = np.empty((13, 301, len(bins)), complex)
    for index, chunk in enumerate(chunks):
        offset = chunk.byte_offset - start
        raw = decode_chunk(blob[offset : offset + chunk.size], dtype, (13, 301))
        symbols[:, :, index] = raw["real"] + 1j * raw["imag"]
    np.savez_compressed(out, symbols=symbols, bins=bins, frame_indices=np.arange(13))
    metadata = dict(
        url=URL,
        etag=remote.etag,
        dataset="yDataSoft",
        fetched_bytes=remote.total,
        shape=list(symbols.shape),
        sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
        limitation="Published corrected/normalized soft constellation estimates, "
        "not raw IQ or independent acquisition. Native FFT bins400..463.",
    )
    out.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
