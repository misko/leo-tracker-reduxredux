import errno
import json
import os
import shutil
import subprocess
from hashlib import sha256
from importlib import import_module
from pathlib import Path

import numpy as np
import pytest

from leo.storage.short_window import ShortWindowWriter

audit = import_module("reports.ALGO08.single-core-2x.storage_io_audit")


def test_inventory_checks_only_bound_manifests_and_rounds_each_file(tmp_path, monkeypatch):
    writer = ShortWindowWriter(
        tmp_path, "sealed", configuration={}, radio={}, receiver_ids=(0,), chunk_windows=1
    )
    for sequence in range(2):
        writer.append(
            sequence=sequence,
            target_id="test",
            samples=np.zeros((16, 1, 2), dtype="<i2"),
            acquisition={},
            powers=({},),
        )
    manifest = writer.finish(stop_reason="test") / "manifest.json"
    read_bytes = Path.read_bytes
    raw = read_bytes(manifest)

    def read(path):
        assert path == manifest
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    case = dict(
        id="test",
        recording=dict(
            window_count=2,
            segments=[
                {
                    "path": str(manifest.relative_to(tmp_path)),
                    "sha256": sha256(raw).hexdigest(),
                }
            ],
        ),
    )
    result = audit.inventory(case, tmp_path, 4096)
    assert result["file_groups"]["compressed_iq"]["pages"] == 2
    assert result["file_groups"]["compressed_iq"]["logical_bytes"] == sum(
        c["compressed_bytes"] for c in json.loads(raw)["chunks"]
    )
    assert result["recording_pages"] == 5
    assert "present_cache_snapshot" not in result
    case["recording"]["segments"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Changed sealed manifest"):
        audit.inventory(case, tmp_path, 4096)


def test_linux_counter_and_elapsed_cpu_gap_use_the_same_saved_pair():
    case = dict(raw_authority="scope", recording=dict(window_count=3))
    arm = dict(
        raw_authority="scope",
        receipt=dict(window_count=3),
        input_blocks=17,
        cpu_s=2.5,
        elapsed_s=4.0,
        voluntary_switches=1,
        involuntary_switches=5,
    )
    result = audit.receipt(
        case,
        dict(
            order=["candidate", "baseline"],
            recording="fixture",
            runs=dict(baseline=arm, candidate=dict(arm, input_blocks=0)),
        ),
        4096,
    )
    assert result["arms"]["baseline"]["charged_page_equivalents"] == 2.125
    assert result["arms"]["baseline"]["non_cpu_s"] == 1.5
    assert result["arms"]["candidate"]["charged_read_bytes"] == 0


def test_optional_cache_query_does_not_read_and_reports_unavailable(tmp_path, monkeypatch):
    path = tmp_path / "payload.zst"
    path.write_bytes(b"x" * 4097)

    def fail(*args):
        raise AssertionError("payload read")

    def denied(fd, length):
        assert os.lseek(fd, 0, os.SEEK_CUR) == 0
        assert length == 4097
        raise PermissionError(errno.EPERM, "fixture")

    monkeypatch.setattr(os, "read", fail)
    result = audit.cache_snapshot([(tmp_path, path.name, 4097)], 4096, denied)
    assert result["cached_pages"] is None
    assert result["unavailable"] == {"EPERM": 1}
    result = audit.cache_snapshot([(tmp_path, path.name, 4097)], 4096, lambda *args: 1)
    assert result["observed_file_pages"] == 2 and result["cached_pages"] == 1


def test_native_cache_helper_on_synthetic_written_pages(tmp_path):
    cc = shutil.which("cc")
    if cc is None:
        pytest.skip("The optional Linux cachestat helper needs a C compiler")
    source = Path(__file__).parents[2] / "tools/pipeline_eval/qualification/cache_residency.c"
    library = tmp_path / "cache.so"
    subprocess.run(
        [
            cc,
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-shared",
            "-fPIC",
            str(source),
            "-o",
            str(library),
        ],
        check=True,
    )
    size = os.sysconf("SC_PAGE_SIZE")
    path = tmp_path / "cache-test"
    path.write_bytes(b"x" * size)
    result = audit.cache_snapshot([(tmp_path, path.name, size)], size, audit._cache_query(library))
    if result["unavailable"].keys() & {"ENOSYS", "EOPNOTSUPP", "EPERM"}:
        pytest.skip("This kernel or filesystem cannot expose cachestat to the test process")
    assert result["cached_pages"] == 1
