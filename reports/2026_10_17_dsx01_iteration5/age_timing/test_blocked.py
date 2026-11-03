import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location('age_blocked', Path(__file__).with_name('blocked.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_metadata_port_ignores_measured_values_and_descriptive_labels():
    rows = [dict(observation_id=str(i), time_s=float(i), actual_rf_hz=11.5e9,
        receiver=1+i%2, channel=1+i%8, measured_cfo_hz=99., original_associated=True)
        for i in range(8)]
    first = module.metadata_from_rows(rows)
    changed = [dict(r, measured_cfo_hz=-123456., original_associated=False) for r in rows]
    second = module.metadata_from_rows(changed)
    assert first.window_ids == second.window_ids
    for name in ('times_s', 'rf_hz', 'receiver', 'channel', 'measured_hz'):
        np.testing.assert_array_equal(getattr(first, name), getattr(second, name))
    assert not first.measured_hz.any()


def test_roles_are_exhaustive_and_boundary_is_separate():
    entries = [dict(global_group_id=str(i), role=role)
               for i, role in enumerate(('train', 'held', 'boundary'))]
    masks = module.role_masks(['0', '1', '2'], entries)
    np.testing.assert_array_equal(masks['train'], [True, False, False])
    np.testing.assert_array_equal(masks['held'], [False, True, False])
    np.testing.assert_array_equal(masks['boundary'], [False, False, True])
    with pytest.raises(ValueError, match='duplicate'):
        module.role_masks(['0', '1', '2'], entries+[entries[0]])
    with pytest.raises(KeyError):
        module.role_masks(['missing'], entries)


def test_incomplete_or_changed_fit_receipt_blocks_prediction(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'HERE', tmp_path)
    for family in ('scalar2', 'age'):
        records = []
        for arm in ('fitted-c', 'zero-c'):
            path = tmp_path/f'{family}-{arm}.json'
            path.write_text(json.dumps(dict(family=family, arm=arm)))
            records.append(dict(path=str(path), sha256=module.digest(path)))
        (tmp_path/f'blocked_seal_{family}.json').write_text(json.dumps(dict(outcomes=records)))
    assert len(module.fit_seals()) == 4
    (tmp_path/'age-zero-c.json').write_text('changed')
    with pytest.raises(ValueError, match='must seal'):
        module.fit_seals()
