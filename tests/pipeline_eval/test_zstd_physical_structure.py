from hashlib import sha256

import numpy as np

from leo.storage import writer
from reports.ALGO08.v3 import zstd_physical_structure as physical


def test_partial_cache_rejects_frame_without_reading_content(tmp_path):
    path = tmp_path / "archive"
    path.write_bytes(b"not cache-admissible")
    admission, view = physical.view_for(tmp_path, (path.name,), lambda fd, size: 0)
    assert view is None
    assert admission["snapshot"]["cached_pages"] == 0
    assert "incomplete residency" in admission["stop"]


def test_reconstructed_frame_checks_every_clip_and_preserves_order(tmp_path):
    inputs = [np.full((200, 2, 2), i, dtype="<i2") for i in (1, 2)]
    visits = [(dict(case="f", visit=i, sha256="sha256:"+sha256(iq).hexdigest()), iq)
              for i, iq in enumerate(inputs)]
    result = physical.reconstruct(visits, tmp_path, writer._CompressedFileWriter, writer.zstd)
    assert result["decoded_sha256"] == sha256(b"".join(iq.tobytes() for iq in inputs)).hexdigest()
    assert [row["visit"] for row in result["visits"]] == [0, 1]
