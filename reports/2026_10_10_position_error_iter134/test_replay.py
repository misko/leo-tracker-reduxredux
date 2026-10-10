from dataclasses import asdict
from types import SimpleNamespace as NS

import numpy as np
import pytest
from mapping import visit_ordinals
from replay import EventStore, original


def setup(ids=(0, 3)):
    visits = [
        NS(
            event=NS(
                visit_index=e,
                valid_start_counter=100000 * e,
                target=NS(channel=1, edge=NS(value="lower")),
            ),
            valid_sample_count=50000,
        )
        for e in ids
    ]
    windows = [
        {
            **asdict(original.Window(str(e), e, 0, 0, 0, 0, 0, 0, 1, 0, True, probe_count=50000)),
            "status": "metadata-ready",
            "channel": 1,
        }
        for e in ids
    ]
    metadata = {
        "session_id": "s",
        "input_manifest_sha256": "hash",
        "sample_rate_hz": 2500000,
        "receiver_ids": [0],
        "window_ids": [str(e) for e in ids],
        "windows": windows,
        "visits": {str(e): {"valid_start_counter": 100000 * e, "sample_count": 50000} for e in ids},
    }
    capture = NS(
        manifest_sha256="hash",
        manifest=NS(
            receipt=NS(
                visits=visits, plan=NS(geometry=NS(sample_rate_hz=2500000, receiver_ids=[0]))
            ),
            chunks=[NS(uncompressed_bytes=200000)],
        ),
    )

    class Reader:
        session = capture
        calls = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read_visit_ci16(self, ordinal):
            self.calls.append(ordinal)
            return visits[ordinal], np.zeros((50000, 1, 2), dtype=np.int16)

    reader = Reader()
    store = NS(reader=lambda session: reader)
    return metadata, visits, reader, store


@pytest.mark.parametrize("ids", [(0, 1), (0, 3)])
def test_frozen_runner_full_membership_through_mapped_public_port(ids):
    metadata, _, reader, store = setup(ids)
    plan = {
        "maximum_chunk_bytes": 64 * 1024**2,
        "maximum_visit_bytes": 32 * 1024**2,
        "maximum_case_seconds": 1200,
    }
    rows = list(
        original.execute(
            metadata,
            plan,
            store=EventStore(store, metadata),
            evaluator=lambda *args: {"parity": "passed"},
        )
    )
    assert [r["window_id"] for r in rows] == list(map(str, ids))
    assert all(r["status"] == "complete" for r in rows)
    assert reader.calls == [0, 1]


@pytest.mark.parametrize("kind", ["duplicate", "absent", "counter", "channel"])
def test_map_rejects_wrong_identity_before_read(kind):
    metadata, visits, reader, store = setup()
    if kind == "duplicate":
        visits[1].event.visit_index = 0
    if kind == "absent":
        visits[1].event.visit_index = 4
    if kind == "counter":
        visits[1].event.valid_start_counter += 1
    if kind == "channel":
        visits[1].event.target.channel = 2
    with pytest.raises(ValueError), EventStore(store, metadata).reader("s"):
        pass
    assert reader.calls == []


def test_mapping_exact_sparse_event_to_ordinal():
    metadata, visits, _, _ = setup()
    assert visit_ordinals(visits, metadata) == {0: 0, 3: 1}
