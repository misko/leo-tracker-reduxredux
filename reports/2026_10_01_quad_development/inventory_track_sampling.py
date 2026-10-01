"""Read-only inventory of retained evidence versus actual fitted point selection."""
import json
from pathlib import Path
import numpy as np
import window_inputs  # Establish frozen research paths.
from common import independent_tracks, make_config
from physics import _spread_indices
from screen_seed_prefix import digest, sealed

HERE = Path(__file__).resolve().parent


def main():
    output = HERE/'track-sampling-inventory-v1.json'
    if output.exists():
        raise FileExistsError(output)
    selection = sealed(HERE/'selection.json')
    config = make_config()
    inputs = {str(HERE/'selection.json'): digest(HERE/'selection.json')}
    rows = []
    for unit in selection['evaluation_units']:
        if unit['size'] != 1:
            continue
        parent = HERE/'independent-v2'/unit['block_id']/(unit['unit_id']+'.json')
        receipt = sealed(parent)
        evidence_path = HERE/'prepared'/unit['scans'][0]/'evidence.json'
        if digest(evidence_path) != receipt['inputs'][str(evidence_path)]:
            raise ValueError('Evidence/fit binding mismatch')
        inputs[str(parent)] = digest(parent)
        inputs[str(evidence_path)] = digest(evidence_path)
        tracks, _ = independent_tracks(json.loads(evidence_path.read_text()))
        expected = []
        for track in tracks:
            times_ns = np.asarray(track['times_utc_ns'], dtype=np.int64)
            times = (times_ns-times_ns.min())/1e9
            chosen = _spread_indices(times, config.max_points)
            ids = track['physical_observation_ids']
            expected.append([ids[i] for i in chosen])
            denser = _spread_indices(times, 16)
            rows.append(dict(unit=unit['unit_id'], dataset=unit['block_id'].split('-')[0],
                             track_id=track['track_id'], available=len(times), used=len(chosen),
                             possible_16=min(16, len(times)), possible_32=min(32, len(times)),
                             original_points_lost_by_naive_16=len(set(chosen)-set(denser)),
                             duration_s=float(np.ptp(times)),
                             selected_median_gap_s=float(np.median(np.diff(times[chosen])))))
        if expected != receipt['observations']:
            raise ValueError('Inventory selection differs from actual baseline observations')
    summary = dict(scans=64, retained_tracks=len(rows), max_points=config.max_points,
                   available=sum(r['available'] for r in rows), used=sum(r['used'] for r in rows),
                   possible_16=sum(r['possible_16'] for r in rows), possible_32=sum(r['possible_32'] for r in rows),
                   tracks_over_8=sum(r['available'] > 8 for r in rows),
                   tracks_losing_original_points_under_16=sum(r['original_points_lost_by_naive_16'] > 0 for r in rows),
                   median_available_points=float(np.median([r['available'] for r in rows])),
                   median_selected_gap_s=float(np.median([r['selected_median_gap_s'] for r in rows])))
    sources = {str(Path(m.__file__).resolve()): digest(m.__file__) for m in
               (window_inputs, __import__('common'), __import__('physics'), __import__('run'), __import__('prior'))}
    sources[str(Path(__file__).resolve())] = digest(__file__)
    result = dict(summary=summary, rows=rows, inputs=inputs, sources=sources,
                  qualification='Retained track evidence only; actual selected IDs match all original single receipts. Counts do not imply independence, accuracy or effective information. No fits or reference coordinates used.')
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
