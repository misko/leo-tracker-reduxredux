from importlib import import_module
import os
from pathlib import Path
from stat import S_ISREG

import pytest

from leo.contracts.fast_standard_analysis import ALGO08, PLOTS
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from tests.storage.test_fast_standard_analysis import publication


@pytest.fixture
def batched(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("batched_png_writeback")


def compact_fixture():
    document, pngs = publication()
    run = "algo08-batched-fixture"
    document.update(schema_version=2, model_version=ALGO08, run_id=run)
    return run, document, {name: pngs[name] + bytes([index]) for index, name in enumerate(PLOTS)}


def test_batch_finishes_every_write_before_distinct_png_syncs_and_renames(batched, monkeypatch, tmp_path):
    run, document, pngs = compact_fixture()
    pngs[PLOTS[-1]] = pngs[PLOTS[0]]
    (tmp_path / "stock").mkdir()
    (tmp_path / "batched").mkdir()
    base = FastStandardAnalysisStore(tmp_path / "stock")
    manifest = base.publish(run, document, pngs)
    store = batched.BatchedPngStore(tmp_path / "batched")
    original = os.fsync
    synced = []

    def inspect(descriptor):
        path = Path(os.readlink(f"/proc/self/fd/{descriptor}"))
        assert store.detail(run)["state"] == "pending"
        if path.suffix == ".png":
            assert {x.read_bytes() for x in path.parent.glob("*.png")} == set(pngs.values())
            synced.append(os.fstat(descriptor).st_ino)
        original(descriptor)

    monkeypatch.setattr(os, "fsync", inspect)
    assert store.publish(run, document, pngs) == manifest
    assert len(set(synced)) == len(synced) == 7
    assert {p.name: p.read_bytes() for p in store.folder(run).iterdir()} == {
        p.name: p.read_bytes() for p in base.folder(run).iterdir()
    }


@pytest.mark.parametrize("exception", [KeyboardInterrupt, OSError])
def test_sync_interrupt_closes_descriptors_cleans_private_stage_and_leaves_run_pending(
    batched, monkeypatch, tmp_path, exception,
):
    run, document, pngs = compact_fixture()
    store = batched.BatchedPngStore(tmp_path)
    descriptors = []
    original = os.fsync

    def interrupted(descriptor):
        assert S_ISREG(os.fstat(descriptor).st_mode)
        assert store.detail(run)["state"] == "pending"
        descriptors.append(descriptor)
        if len(descriptors) == 2:
            raise exception("interrupted sync")
        original(descriptor)

    with monkeypatch.context() as scope:
        scope.setattr(os, "fsync", interrupted)
        with pytest.raises(exception, match="interrupted sync"):
            store.publish(run, document, pngs)
    assert store.detail(run)["state"] == "pending"
    assert list(store.base_folder(run).iterdir()) == []
    for descriptor in descriptors:
        with pytest.raises(OSError):
            os.fstat(descriptor)
    assert len(store.publish(run, document, pngs)["artifacts"]) == 8


def test_invalid_last_figure_leaves_no_visible_or_private_publication(batched, tmp_path):
    run, document, pngs = compact_fixture()
    pngs[PLOTS[-1]] = b"not a PNG"
    store = batched.BatchedPngStore(tmp_path)
    with pytest.raises(ValueError, match="PNG required"):
        store.publish(run, document, pngs)
    assert store.detail(run)["state"] == "pending"
    assert list(store.base_folder(run).iterdir()) == []


def test_mismatched_bytes_with_same_digest_fail_before_atomic_rename(batched, monkeypatch, tmp_path):
    run, document, pngs = compact_fixture()
    store = batched.BatchedPngStore(tmp_path)
    monkeypatch.setattr(batched, "digest", lambda _: "sha256:collision")
    with pytest.raises(ValueError, match="Figure digest collision"):
        store.publish(run, document, pngs)
    assert store.detail(run)["state"] == "pending"
    assert list(store.base_folder(run).iterdir()) == []
