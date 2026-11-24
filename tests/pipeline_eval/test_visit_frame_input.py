from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def port(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2]/"reports/ALGO08/v3"))
    import visit_frame_input

    return visit_frame_input


def configuration(path, port):
    recording = path/"fresh-capture"
    folder = recording/"segment-00000000"
    folder.mkdir(parents=True)
    side = folder/"visit-frames-000000.json"
    side.write_text("sealed table")
    a, b = ("sha256:"+letter*64 for letter in "ab")
    member = dict(chunk_index=0, first_sequence=0, window_count=2, compressed_bytes=400,
                  compressed_sha256=a, index_sha256=b, uncompressed_sha256=b,
                  side_name=side.name, side_sha256=a)
    segment = dict(directory=folder.name, window_count=2, manifest_sha256=a, members=[member])
    plan = dict(schema=port.SCHEMA, recording=str(recording), inventory_sha256=b,
                session_id="fast-"+b[7:39], window_count=2, raw_authority=a, segments=[segment])
    return plan, recording, folder


def test_authority_is_external_and_must_match_inventory(tmp_path, port):
    plan, recording, folder = configuration(tmp_path, port)
    authority = tmp_path/"capture-authority.json"
    raw = json.dumps(plan).encode()
    authority.write_bytes(raw)
    digest = "sha256:"+sha256(raw).hexdigest()
    assert port.custody(authority, digest, recording) == plan
    inventory = dict(window_count=2, segments=[dict(path=str(folder), windows=2, manifest_digest=plan["raw_authority"])])
    port.bind_inventory(plan, plan["session_id"], plan["inventory_sha256"], inventory)
    with pytest.raises(ValueError, match="actual ordinary inventory"):
        port.bind_inventory(plan, plan["session_id"], plan["raw_authority"], inventory)
    authority.write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="independently trusted"):
        port.custody(authority, digest, recording)


def test_demands_one_checked_prefix_per_stereo_visit_and_no_invalid_decode(tmp_path, port):
    plan, _, folder = configuration(tmp_path, port)
    commitment = plan["segments"][0]["members"][0]
    chunk = SimpleNamespace(**commitment)
    calls, audit = [], []

    class Ordinary:
        def __init__(self, entry):
            self.targets = {1: dict(channel=1)}
            self.start_sequence, self.stop_sequence = 0, 2
            self.reader = SimpleNamespace(path=folder, manifest_sha256=entry["manifest_digest"],
                manifest=SimpleNamespace(sample_rate_hz=10_000_000, chunks=[chunk]))

    class CheckedMember:
        def __init__(self, reader, pin, *, chunk, side_name):
            assert reader.path == folder and pin == commitment["side_sha256"] and side_name == commitment["side_name"]
            assert chunk is reader.manifest.chunks[0]
            self.authentication = self.metadata = {}
            self.counts = {"authenticated_encoded_bytes": chunk.compressed_bytes}
            self.rows = [SimpleNamespace(sequence=i, target_id=1, iq_sha256=pin, acquisition={}, sample_count=n)
                         for i, n in enumerate((200_000, 3))]
            calls.append("authenticated")

        def read(self, row, *, full):
            calls.append((row.sequence, full))
            self.counts["full_checks" if full else "prefix_checks"] = 1
            return np.zeros((200_000 if full else 80_000, 2, 2), dtype="<i2")

    source, _ = port.source_class(Ordinary, plan, audit, CheckedMember)
    windows = source(dict(path=str(folder), manifest_digest=plan["raw_authority"])).windows()
    first = next(windows)
    assert calls == ["authenticated"] and first.samples.shape == (200_000, 2, 2)
    assert first.samples.realize(False) is first.samples.realize(False)
    with pytest.raises(ValueError, match="cannot change"):
        first.samples.realize(True)
    assert next(windows).samples.shape == (3, 2, 2)
    assert list(windows) == []
    assert calls == ["authenticated", (0, False)] and audit[0]["counts"]["prefix_checks"] == 1


def test_opt_in_preserves_ordinary_and_rejects_mixed_storage_flags():
    from reports.ALGO08.v3.exact_named_raw import visit_frame_scope

    with ExitStack() as scope:
        assert visit_frame_scope(SimpleNamespace(), scope) is None
        with pytest.raises(ValueError, match="own trusted authority"):
            visit_frame_scope(SimpleNamespace(visit_frame_custody=Path("unused"), visit_frame_custody_sha256="pin",
                                              strict_packed_eight=True), scope)
