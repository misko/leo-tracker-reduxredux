from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from runpy import run_path

import numpy as np
import pytest

from leo.storage.errors import BundleCorruptionError
from reports.ALGO08.v3.prefetch_archive_accounting import characterize, PREFETCH_PIN
from reports.ALGO08.v3.prefetch_snapshot_accounting import AlternatingSnapshots, PrefetchAccounting


def test_two_live_snapshot_exports_survive_producer_reuse_and_close():
    pool = AlternatingSnapshots(32)
    with ThreadPoolExecutor(max_workers=1) as worker:
        def submit(size, value):
            owner = pool.borrow(size, dtype=np.uint8)
            owner[:] = value
            return np.frombuffer(memoryview(owner).toreadonly(), dtype=np.uint8)

        first = worker.submit(submit, 8, 7).result()
        second = worker.submit(submit, 8, 19).result()
        refused = worker.submit(submit, 8, 22).result()
        assert len({x.ctypes.data for x in (first, second, refused)}) == 3
        assert (first == 7).all() and (second == 19).all()
        pointer = second.ctypes.data
        del second
        reused = worker.submit(submit, 8, 93).result()
        assert reused.ctypes.data == pointer
        pool.close()
        later = worker.submit(submit, 8, 33).result()
        assert later.ctypes.data not in (first.ctypes.data, reused.ctypes.data)
        assert (first == 7).all() and (reused == 93).all()


@pytest.mark.parametrize("reuse", (False, True))
def test_pinned_attribution_preserves_check_failure_and_exact_retry(tmp_path, reuse):
    root = Path(__file__).resolve().parents[2]
    source = root / "tools/pipeline_eval/variants/experimental/receiver_ingress.py"
    accounting = PrefetchAccounting(reuse)
    accounting.active = []
    descriptor = accounting.descriptor(run_path(str(source))["read_regular_descriptor"])
    path = tmp_path / "member.ci16.zst"
    path.write_bytes(b"exact original bytes")
    with path.open("rb") as stream, pytest.raises(BundleCorruptionError, match="declared bound"):
        descriptor(stream.fileno(), 1)
    assert [row["operation"] for row in accounting.active] == ["descriptor_fstat"]
    accounting.active.clear()
    with path.open("rb") as stream:
        stream.seek(1)
        with pytest.raises(BundleCorruptionError, match="ended while reading"):
            descriptor(stream.fileno(), 30)
    assert [r["bytes"] for r in accounting.active if r["operation"] == "readv"] == [19, 0]
    accounting.active.clear()
    with path.open("rb") as stream:
        result = descriptor(stream.fileno(), 30)
    assert result.readonly and bytes(result) == b"exact original bytes"
    assert [(r["operation"], r["bytes"]) for r in accounting.active] == [
        ("descriptor_fstat", None), ("allocate", None), ("readv", 20),
        ("eof_read", None), ("descriptor_fstat", None),
    ]


def test_archived_grouping_requires_measured_successful_prefetch(tmp_path):
    from json import dumps

    def member(index, size):
        return dict(chunk_index=index, encoded=size, complete_encoded_auth=dict(cpu_ns=10, wall_ns=20, input_blocks=1))

    def write(name, value):
        (tmp_path / name).write_text(dumps(value))

    stats = dict(submitted=1, hits=1, hit_bytes=40, fallback=0)
    source = dict(finished_raw_authority="id", members=[member(0, 30), member(1, 40), member(0, 50)])
    write("legacy-original-acquisition.json", source)
    audit = dict(native_sha256="signed", prefetch_sources=dict(receiver_member_prefetch=PREFETCH_PIN),
                 phases=dict(authenticated_raw_acquisition={}), prefetch=stats,
                 receiver_audit=dict(recording_authority="id", native=dict(native_cpu_ns={}, native_wall_ns={})))
    write("unified-short-bootstrap.json", audit)
    accepted = characterize(tmp_path, identity=("id", "signed"))
    assert accepted["demand"]["bytes"] == 80
    assert accepted["speculative"]["positive_input_block_members"] == 1
    with pytest.raises(ValueError, match="changed source"):
        characterize(tmp_path, identity=("wrong", "signed"))
    stats["fallback"] = 1
    write("unified-short-bootstrap.json", audit)
    with pytest.raises(ValueError, match="Cannot identify"):
        characterize(tmp_path)
