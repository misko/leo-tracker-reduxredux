from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from leo.application.wp11_legacy import WP11LegacyOracleCampaignRunner
from leo.storage import PinnedLocalRoot


class _TinyReader:
    receiver_ids = (1,)
    sample_count = 3

    def iter_blocks(self, *, block_samples: int):
        assert block_samples == 1_000_000
        yield SimpleNamespace(
            metadata=SimpleNamespace(session_sample_start=0, sample_count=3),
            samples=np.array(
                [
                    [[1, -1]],
                    [[2, -2]],
                    [[3, -3]],
                ],
                dtype=np.int16,
            ),
        )


def test_materialize_is_anonymous_after_verified_stream_copy(tmp_path: Path) -> None:
    spool_path = tmp_path / "spool"
    spool_path.mkdir()
    spool = PinnedLocalRoot(spool_path)
    runner = object.__new__(WP11LegacyOracleCampaignRunner)
    runner._spool = spool.clone()  # type: ignore[attr-defined]
    try:
        descriptor, digest = runner._materialize(_TinyReader())  # type: ignore[arg-type]
        try:
            payload = os.read(descriptor, 1024)
        finally:
            os.close(descriptor)
        expected = np.array([[1, -1], [2, -2], [3, -3]], dtype="<i2").tobytes()
        assert payload == expected
        assert digest == f"sha256:{hashlib.sha256(expected).hexdigest()}"
        assert tuple(spool_path.iterdir()) == ()
    finally:
        runner._spool.close()  # type: ignore[attr-defined]
        spool.close()
