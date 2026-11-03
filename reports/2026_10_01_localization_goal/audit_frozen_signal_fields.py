"""Inventory signal-identification evidence actually persisted in the64 frozen exports."""
import json
from collections import Counter
from pathlib import Path

from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    freeze = HERE/'regression-v1-freeze.json'
    assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
    frozen = json.loads(freeze.read_text())
    verify_sources(frozen['source_sha256'])
    rows, fields = [], Counter()
    for unit in frozen['ordered_units']:
        parent_path = next((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
        assert digest(parent_path) == json.loads(parent_path.with_suffix('.seal.json').read_text())[
            'prediction_sha256']
        parent = json.loads(parent_path.read_text())
        candidates = [Path(p) for p in parent['inputs'] if p.endswith('observations.json')]
        assert len(candidates) == 1
        path = candidates[0]
        assert digest(path) == parent['inputs'][str(path)]
        observations = json.loads(path.read_text())
        for track in observations['tracks']:
            fields.update(track.keys())
        rows.append(dict(unit=unit, source_path=str(path), source_sha256=digest(path),
                         exported_tracks=len(observations['tracks']),
                         retained_tracks=len(parent['observations']),
                         retained_samples=sum(map(len, parent['observations'])),
                         source_manifest=observations['manifest_sha256'],
                         analysis_manifest=observations['analysis_manifest_sha256']))
    total = sum(r['exported_tracks'] for r in rows)
    absent = [key for key in ['candidate_ids', 'source_group_ids', 'exact_score', 'control_score',
                             'margin', 'standard_uncertainty_hz', 'support_start_utc_ns',
                             'decoded_satellite_id', 'verified_norad_id'] if key not in fields]
    result = dict(
        planned=64, audited=len(rows), exported_tracks=total,
        retained_tracks=sum(r['retained_tracks'] for r in rows),
        retained_sample_entries=sum(r['retained_samples'] for r in rows),
        track_field_presence=dict(fields), absent_track_fields=absent, rows=rows,
        source_sha256=digest(__file__), original_freeze_sha256=digest(freeze),
        qualification='Schema/evidence inventory, not signal rejection. Exact source and parent '
        'hashes checked for every scan. Missing fields do not imply absent underlying '
        'detector evidence. Doppler fit identities must not be treated as decoded satellite IDs. '
        'No measurements or benchmark membership changed; no GPS read.')
    output = HERE/'frozen-signal-fields-v1.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))


if __name__ == '__main__':
    main()
