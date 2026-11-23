import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'reports/ALGO08/v3'))

from cumulative_grid_projection import saved_inventory_port
import joint_publication
from leo.contracts.digests import canonical_digest
from leo.storage.fast_scan import FastScanStore
from leo.storage.short_window import ShortWindowReader
from mixed_named_finish_0008 import ARMS, sidecars


def test_saved_port_restores_original_ports_and_only_admits_bound_metadata(tmp_path, monkeypatch):
    def publication(_args, **options):
        return options

    monkeypatch.setattr(joint_publication, 'run', publication)
    recording = tmp_path / 'original'
    manifest = dict(recording_name=recording.name, window_count=5,
                    segments=[dict(path=str(recording / 'signed'), windows=5)])
    path = tmp_path / 'inventory.json'
    path.write_text(json.dumps(manifest))
    pin = canonical_digest(manifest)
    session = 'fast-' + pin[7:39]
    fields = dict(recording=str(recording), inventory=pin, session=session, saved_inventory=str(path))
    original_inventory, original_reader = FastScanStore.inventory, ShortWindowReader.__init__
    with saved_inventory_port(fields) as staged:
        assert staged
        store = FastScanStore(tmp_path / 'output')
        assert store.inventory(recording, verify_windows=False) == (session, pin, manifest)
        with pytest.raises(ValueError, match='metadata'):
            store.inventory(recording)
        with pytest.raises(ValueError, match='metadata'):
            store.inventory(tmp_path / 'other', verify_windows=False)
        with pytest.raises(RuntimeError, match='waveform'):
            ShortWindowReader(recording)
        detector = joint_publication.run(None)['detector_override']
        with pytest.raises(RuntimeError, match='waveform'):
            detector()
    assert FastScanStore.inventory is original_inventory
    assert ShortWindowReader.__init__ is original_reader
    assert joint_publication.run is publication
    with saved_inventory_port({}) as staged:
        assert not staged
        assert FastScanStore.inventory is original_inventory
    with pytest.raises(ValueError, match='original recording'):
        with saved_inventory_port(dict(fields, inventory='sha256:'+'0'*64)):
            pytest.fail('A mismatched digest opened the publication scope')


def test_scientific_sidecars_require_179_points_both_arms_and_own_png():
    png = 'sha256:' + 'a' * 64
    images = dict(position={'sha256': png}, **{f'figure{i}': {} for i in range(7)})
    grid = dict(complete=True, evaluated_points=179, points=list(range(179)), binding={'position_png_sha256': png})
    stages = [dict(arms={name: {'endpoint': [1.0, 2.0]} for name in ARMS})]
    path = dict(stages=stages, binding={'position_png_sha256': png})
    store = SimpleNamespace(position_grid=lambda _: grid, position_path=lambda _: path)
    observed, evidence = sidecars(store, 'run', images)
    assert observed is grid
    assert evidence['position_png'] == {'grid': png, 'path': png}
    assert evidence['path_stages'] == 1
    path['binding']['position_png_sha256'] = 'sha256:' + 'b' * 64
    with pytest.raises(ValueError, match='own published PNG'):
        sidecars(store, 'run', images)
    path['binding']['position_png_sha256'] = png
    stages[0]['arms'].pop('c0')
    with pytest.raises(ValueError, match='full grid, path and eight figures'):
        sidecars(store, 'run', images)
