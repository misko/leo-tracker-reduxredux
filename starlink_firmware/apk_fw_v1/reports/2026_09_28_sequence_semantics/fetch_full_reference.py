"""Bounded coalesced-range extraction of the first 13 published full-band frames."""

import hashlib
import json
import sys
import time
import zlib
from pathlib import Path

import h5py
import numpy as np

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str((BASE.parents[3] / "reports") / "2026_09_27_ds7_header"))
from fetch_ut_reference import URL, Remote  # noqa: E402


def decode_chunk(compressed, dtype, shape):
    decoded = zlib.decompress(compressed)
    if len(decoded) != np.prod(shape) * np.dtype(dtype).itemsize:
        raise ValueError("Unexpected decompressed chunk length")
    return np.frombuffer(decoded, dtype=dtype).reshape(shape)


def main():
    out = BASE / "local/full-reference-0-12.npz"
    if out.exists():
        raise FileExistsError("Existing reference cache retained; inspect before replacing")
    remote = Remote()
    with h5py.File(remote, "r") as source:
        dataset = source["yDataDec"]
        assert dataset.shape == (1009, 301, 1024)
        assert dataset.chunks == (13, 301, 1)
        plist = dataset.id.get_create_plist()
        assert plist.get_nfilters() == 1 and plist.get_filter(0)[0] == 1
        dtype = dataset.dtype
        chunks = [dataset.id.get_chunk_info_by_coord((0, 0, b)) for b in range(1024)]
        assert all(c.filter_mask == 0 and c.size > 0 for c in chunks)
        first = min(c.byte_offset for c in chunks)
        last = max(c.byte_offset + c.size for c in chunks)
        if last - first > 12 * 1024**2:
            raise ValueError("Chunk group exceeds bounded coalesced range")
        print(f"Fetching {last - first} bytes for 13 complete frames", flush=True)
        remote.seek(first)
        blob = remote.read(last - first)
    symbols = np.empty((13, 301, 1024), complex)
    for b, c in enumerate(chunks):
        offset = c.byte_offset - first
        raw = decode_chunk(blob[offset : offset + c.size], dtype, (13, 301))
        symbols[:, :, b] = raw["real"] + 1j * raw["imag"]
    np.savez_compressed(out, symbols=symbols, bins=np.arange(1024), frame_indices=np.arange(13))
    # Compare all overlapping cached carriers to independently extracted ranges.
    overlap = []
    cache = (BASE.parents[3] / "reports") / "2026_09_28_ds7_ds8_correspondence/local/ut-codebook"
    for start in [100, 200]:
        old = np.load(cache / f"bins-{start}.npz")
        exact = np.array_equal(symbols[:, :, old["bins"]], old["symbols"][:13], equal_nan=True)
        if not exact:
            raise ValueError("Coalesced extraction disagrees with existing carrier cache")
        overlap.append(dict(start=start, exact=exact, symbols=int(old["symbols"][:13].size)))
    metadata = dict(
        url=URL,
        etag=remote.etag,
        dataset="yDataDec",
        array_indices=[0, 12],
        shape=list(symbols.shape),
        fetched_bytes=remote.total,
        elapsed_seconds=time.monotonic() - remote.started,
        range_start=first,
        range_stop_exclusive=last,
        overlap_checks=overlap,
        sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
        limitation="Published hard constellation symbols, not raw IQ or FEC-decoded data.",
    )
    out.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
