from hashlib import sha256
from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("saved_overhead"), import_module("verified_png_reads")


def test_exclusive_timing_assigns_nested_work_once(modules, monkeypatch):
    profiler, _ = modules
    stamps = iter(((0, 0), (1, 1), (3, 3), (6, 6), (8, 8), (10, 10)))
    monkeypatch.setattr(profiler, "now", lambda: next(stamps))
    ledger = profiler.Ledger()
    with ledger.stage("persist"):
        with ledger.stage("fsync"):
            pass
    out = ledger.finish()
    assert {key: value["cpu_ns"] for key, value in out.items()} == {"remaining": 3, "persist": 4, "fsync": 3}


def test_only_previously_verified_same_run_figure_is_reused(modules, tmp_path):
    _, module = modules
    reads, decodes = [], []

    class Store:
        def __init__(self, root):
            self.root = root

        def artifact(self, run, name, expected):
            data = f"{run}/{name}".encode()
            digest = "sha256:" + sha256(data).hexdigest()
            if expected != digest:
                raise ValueError("unauthorized or changed bytes")
            reads.append((self.root, run, name))
            return data

    def decode(image, digest):
        decodes.append(image)
        return dict(sha256=digest)

    root = tmp_path / "fresh"
    stat = {}
    reuse = module.VerifiedPngReads(root, decode, stat)
    first = Store(root)
    picture = "sha256:" + sha256(b"run/position").hexdigest()
    with reuse.capture(Store):
        assert first.artifact("run", "position", picture) == b"run/position"
        with pytest.raises(ValueError, match="unauthorized"):
            first.artifact("run", "position", "incorrect")
    assert reuse.read(first, "run", "position", picture) == dict(sha256=picture)
    assert len(reads) == len(decodes) == 1
    assert reuse.read(Store(tmp_path / "other"), "run", "position", picture) == dict(sha256=picture)
    assert len(reads) == len(decodes) == 2
    assert stat == {"verified": 1, "reused": 1, "fallbacks": 1, "verified_bytes": len(b"run/position")}


def test_existing_publication_is_not_eligible_for_read_reuse(modules, tmp_path):
    _, module = modules
    with pytest.raises(ValueError, match="fresh publication"):
        module.VerifiedPngReads(tmp_path, None, {})
