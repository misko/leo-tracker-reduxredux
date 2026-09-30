"""Fetch 65 additional public header frames, with range caps and checkpoints."""

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
from fetch_full_reference import URL, Remote, decode_chunk

BASE = Path(__file__).resolve().parent


def main():
    out = BASE / "local/header-reference-0-77.npz"
    if out.exists():
        raise FileExistsError("Existing header sample retained")
    prior_path = BASE / "local/full-reference-0-12.npz"
    prior = np.load(prior_path)
    etag = json.loads(prior_path.with_suffix(".json").read_text())["etag"]
    blocks = [prior["symbols"][:, 1:7]]
    checkpoints = BASE / "local/header-rank-download"
    checkpoints.mkdir(exist_ok=True)
    total = 0
    for first_frame in range(13, 78, 13):
        saved = checkpoints / f"frames-{first_frame}.npz"
        if saved.exists():
            cache = np.load(saved)
            if str(cache["etag"]) != etag:
                raise ValueError("Source ETag differs from cached block")
            blocks.append(cache["symbols"])
            continue
        remote = Remote()
        if remote.etag != etag:
            raise ValueError("Public reference changed")
        with h5py.File(remote, "r") as source:
            data = source["yDataDec"]
            assert data.shape == (1009, 301, 1024) and data.chunks == (13, 301, 1)
            filters = data.id.get_create_plist()
            assert filters.get_nfilters() == 1 and filters.get_filter(0)[0] == 1
            dtype = data.dtype
            chunks = [data.id.get_chunk_info_by_coord((first_frame, 0, b)) for b in range(1024)]
            assert all(c.filter_mask == 0 and c.size > 0 for c in chunks)
            start = min(c.byte_offset for c in chunks)
            stop = max(c.byte_offset + c.size for c in chunks)
            if stop - start > 12 * 1024**2 or total + stop - start > 60 * 1024**2:
                raise ValueError("Header sample exceeds bounded transfer")
            remote.seek(start)
            blob = remote.read(stop - start)
        symbols = np.empty((13, 6, 1024), complex)
        for b, c in enumerate(chunks):
            offset = c.byte_offset - start
            decoded = decode_chunk(blob[offset : offset + c.size], dtype, (13, 301))
            symbols[:, :, b] = decoded["real"][:, 1:7] + 1j * decoded["imag"][:, 1:7]
        np.savez_compressed(saved, symbols=symbols, etag=etag)
        blocks.append(symbols)
        total += remote.total
        print(first_frame, "through", first_frame + 12, "fetched", total, flush=True)
    np.savez_compressed(
        out,
        symbols=np.concatenate(blocks),
        bins=np.arange(1024),
        frame_indices=np.arange(78),
        ofdm_symbols=np.arange(2, 8),
    )
    metadata = dict(
        url=URL,
        etag=etag,
        dataset="yDataDec",
        fetched_bytes_this_run=total,
        prior_sha256=hashlib.sha256(prior_path.read_bytes()).hexdigest(),
        sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
        limitation="Published hard decisions from same acquisition; first13 reused. "
        "No new RF, no FEC-decoded header or independent acquisition.",
    )
    out.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    main()
