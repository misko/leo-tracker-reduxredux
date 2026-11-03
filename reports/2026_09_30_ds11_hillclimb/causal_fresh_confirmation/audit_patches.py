"""Independent completeness/slot audit required before fresh confirmation fits."""
import hashlib
import json
from pathlib import Path

import numpy as np

import confirmation_model as model

HERE = Path(__file__).resolve().parent


def main():
    paths = [HERE/'plan.json', HERE/'catalogue_identities.json',
             HERE.parent/'remaining43_causal_inventory/inventory.json', Path(__file__),
             HERE/'confirmation_model.py']
    plan, identities, inventory = [json.loads(p.read_text()) for p in paths[:3]]
    assert identities['plan_sha256'] == model.core.digest(paths[0])
    rows = []
    for slot, entry in enumerate(plan['inputs']):
        index = entry['full_manifest_index']
        path = HERE/'patches'/f'{index:02d}.json'
        patch = json.loads(path.read_text())
        paths.extend([path, Path(patch['array']['path'])])
        doc = model.core.fast.load_documents(dict(config=plan['config'], inputs=[entry]))[0]
        patched = model.build_model([doc], plan['config'], 'fresh', index)
        side = identities['scans'][str(slot)]
        assert side['full_manifest_index'] == index and side['session_id'] == doc['session_id']
        comparison = next(r for r in inventory['comparisons'] if r['full_manifest_index'] == index)
        changed = {r['norad']:r for r in comparison['three_day_best_capture_vs_latest_provider_guard']['changes']}
        by_track = {r['track_id']:r for r in patch['tracks']}
        assert len(by_track) == len(patch['tracks'])
        expected_tracks = set()
        count = 0
        manifest_path = next(Path(a['path']) for a in entry['artifacts']
                             if a['kind'] == 'candidates' and a['path'].endswith('.json'))
        bank_path = next(Path(a['path']) for a in entry['artifacts']
                         if a['kind'] == 'candidates' and a['path'].endswith('.npz'))
        assert model.core.digest(manifest_path) == side['manifest_sha256']
        assert model.core.digest(bank_path) == side['bank_sha256']
        with np.load(patch['array']['path'], allow_pickle=False) as arrays, np.load(bank_path, allow_pickle=False) as old:
            expected_keys = set()
            for ti, track in enumerate(doc['tracks']):
                identity = side['tracks'][track['track_id']]
                assert identity['index'] == ti
                ids = np.asarray(identity['candidate_ids'])
                norads = np.asarray(identity['candidate_norad'])
                np.testing.assert_array_equal(ids, old[f'candidate_ids_{ti}'])
                slots = np.flatnonzero(np.isin(norads, list(changed)))
                if not len(slots):
                    assert track['track_id'] not in by_track
                    continue
                expected_tracks.add(track['track_id'])
                row = by_track[track['track_id']]
                assert row['index'] == ti
                np.testing.assert_array_equal(arrays[row['slots_key']], slots)
                np.testing.assert_array_equal(row['candidate_ids'], ids[slots])
                np.testing.assert_array_equal(row['norads'], norads[slots])
                assert len(row['records']) == len(slots)
                assert row['training_mask_sha256'] == hashlib.sha256(track['mask'].astype(np.uint8).tobytes()).hexdigest()
                for j, record in enumerate(row['records']):
                    assert record['candidate_id'] == ids[slots[j]] and record['norad'] == norads[slots[j]]
                    for key in ('original_snapshot', 'selected_snapshot', 'original_element_sha256', 'selected_element_sha256'):
                        assert record[key] == changed[record['norad']][key]
                expected_keys.update(row[k] for k in ('slots_key','position_key','velocity_key'))
                count += len(slots)
            assert set(arrays.files) == expected_keys
        assert set(by_track) == expected_tracks
        assert patched.metadata['changed_slots'] == count == patch['counts']['replacement_candidate_occurrences']
        if not count:
            assert not patch['tracks'] and not patch['records'] and not patch['proofs'] and not patch['selected_snapshots']
        assert patch['replay']['position_max_abs_km'] <= 1e-8
        assert patch['replay']['velocity_max_abs_km_s'] <= 1e-10
        rows.append(dict(index=index, tracks=len(expected_tracks), changed_slots=count,
                         patch_sha256=model.core.digest(path), array_sha256=model.core.digest(patch['array']['path']),
                         status='passed'))
    output = dict(schema='ds11-causal-confirmation-pre-fit-patch-audit/v1', rows=rows,
                  status='passed', source_sha256={str(p):model.core.digest(p) for p in paths})
    with (HERE/'patch-audit.json').open('x') as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
