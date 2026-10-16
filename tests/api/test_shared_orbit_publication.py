import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from leo.api.fast_scan_orbits import fast_scan_orbit_router
from leo.contracts.fast_scan_orbits import PLOT_NAMES
from leo.storage.fast_scan import FastScanStore
from leo.storage.shared_fast_scan import SharedFastScanStore


def test_shared_precedence_and_legacy_bytes_remain_immutable(tmp_path):
    old = FastScanStore(tmp_path)
    shared = SharedFastScanStore(tmp_path, 'shared-scan-q-v2')
    old_png = b'\x89PNG\r\n\x1a\nold'
    new_png = b'\x89PNG\r\n\x1a\nshared'
    old.publish_orbits('run', dict.fromkeys(PLOT_NAMES, old_png), {'stage': 'legacy'})
    app = FastAPI()
    app.include_router(fast_scan_orbit_router(old, shared))
    api = TestClient(app)
    path = '/api/v1/fast-scans/run/orbits'
    assert api.get(path).json()['provenance']['stage'] == 'legacy'
    shared.orbit_store().publish_orbits('run', dict.fromkeys(PLOT_NAMES, new_png), {'stage': 'shared'})
    assert api.get(path).json()['provenance']['stage'] == 'shared'
    assert api.get(path + '/ch1-4-all.png').content == new_png
    assert old.orbit_artifact('run', 'ch1-4-all') == old_png
    assert SharedFastScanStore(tmp_path, 'another-model').orbit_manifest('run')['artifacts'] == []
    with pytest.raises(ValueError):
        shared.orbit_store().publish_orbits('run', dict.fromkeys(PLOT_NAMES, old_png), {})


def test_missing_shared_root_read_does_not_create(tmp_path):
    root = tmp_path / 'absent'
    assert SharedFastScanStore(root, 'v2').orbit_manifest('run') == {'artifacts': []}
    assert not root.exists()
