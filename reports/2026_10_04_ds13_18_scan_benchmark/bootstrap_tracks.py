"""Initialize the shared RX calibration from long refined track shapes.

Conditional known-roof bootstrap, NOT blind identity or position validation.
All near-visible satellite IDs are considered for each track; no production
rank-one identity or A/B-specific receiver calibration is imported.
"""
import argparse
import dataclasses
import inspect
import json
import time
from pathlib import Path

import numpy as np

from cohort import digest
from numeric_data import enable_research_model, load
from refinement import ALIAS_HZ, circular


def reconstruct(data, directory):
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories, PersistentHopTrajectoryConfig
    original = json.loads((directory/'observations.json').read_text())
    store = ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:
        source = store.load(data.session_id)
    finally:
        store.close()
    if source.input_manifest_sha256 != original['signature']['manifest_sha256'] or source.analysis_manifest_sha256 != original['analysis_manifest_sha256']:
        raise ValueError('tracking input changed after export')
    live = {p.candidate_id:p for p in project_scanner_candidates(source)}
    metadata = {r['row_index']:r for r in original['records']}
    refined = {r['row_index']:r for r in json.loads((directory/'refinement/refined.json').read_text())['records']}
    points, lookup, nonpositive = [], {}, []
    for i, original_row in enumerate(data.original_rows):
        row = metadata[int(original_row)]
        point = live[row['candidate_id']]
        if data.margin[i] <= 0:
            nonpositive.append(int(original_row))
            continue
        fit = refined[int(original_row)]['refinement']
        exact = fit['exact'] if fit['status'] == 'refined' else row['original_exact_score']
        control = fit['control'] if fit['status'] == 'refined' else row['original_control_score']
        points.append(dataclasses.replace(point, measured_cfo_hz=float(data.measured[i]), margin=float(data.margin[i]),
                                          exact_score=exact, control_score=control))
        lookup[point.candidate_id] = i
    config = PersistentHopTrajectoryConfig()
    result = reconstruct_persistent_hop_trajectories(tuple(points), config=config)
    tracks = []
    for track in result.tracklets:
        rows = sorted({lookup[p.candidate_id] for p in track.points}, key=lambda i:data.times[i])
        if len(rows) < 15 or np.ptp(data.times[rows]) < 15:
            continue
        tracks.append(dict(track_id=str(track.tracklet_id), rows=rows, receiver=int(data.receiver[rows[0]]),
                           span_s=float(np.ptp(data.times[rows])), channel=int(data.channel[rows[0]])))
    chosen = []
    for rx in (0,1):
        chosen.extend(sorted([r for r in tracks if r['receiver']==rx], key=lambda r:(-r['span_s'],r['track_id']))[:12])
    return chosen, dict(configuration=dataclasses.asdict(config), all_tracks=len(result.tracklets),
                        supported_tracks=len(tracks), chosen_tracks=len(chosen), bootstrap_only_nonpositive_rows=nonpositive,
                        sources={str(Path(inspect.getfile(obj))):digest(Path(inspect.getfile(obj)).read_bytes())
                                 for obj in (project_scanner_candidates,reconstruct_persistent_hop_trajectories,ScannerTrackingInputStore)})


def identify_tracks(data, tracks):
    """Shape-only timing sweep, with a free constant solely for initialization."""
    enable_research_model()
    from track_seed import robust_locations, loss
    results = []
    for track in tracks:
        rows = np.asarray(track['rows'], int)
        unwrapped = np.unwrap(data.measured[rows]*2*np.pi/ALIAS_HZ)*ALIAS_HZ/(2*np.pi)
        best = []
        for offset in np.arange(-20.,20.001,2.):
            parameters = data.initial.copy()
            parameters[6:] = offset
            for begin in range(0,len(data.numbers),128):
                satellites = np.arange(begin,min(begin+128,len(data.numbers)))
                prediction, visible = data.predict(parameters, rows=np.repeat(rows,len(satellites)),
                                                   satellites=np.tile(satellites,len(rows)))
                prediction, visible = prediction.reshape(len(rows),-1), visible.reshape(len(rows),-1)
                values = unwrapped[:,None]-prediction
                constants = robust_locations(values)
                costs = np.mean(loss(values-constants),axis=0)
                rms = np.sqrt(np.mean((values-constants)**2,axis=0))
                costs[np.mean(visible,axis=0)<.9] = np.inf
                for local in np.argsort(costs)[:3]:
                    if not np.isfinite(costs[local]):
                        continue
                    best.append(dict(satellite_index=int(satellites[local]), catalog_number=int(data.numbers[satellites[local]]),
                                     offset_s=float(offset), constant_offset_hz=float(circular(constants[local])),
                                     shape_cost=float(costs[local]), shape_rms_hz=float(rms[local])))
        ranked = sorted(best,key=lambda r:(r['shape_cost'],abs(r['offset_s']),r['catalog_number']))
        if not ranked:
            continue
        selected = dict(track, **ranked[0], alternatives=ranked[:5], accepted=ranked[0]['shape_rms_hz']<2000.,
                        source_groups=len(rows), center_s=float(np.mean(data.times[rows])))
        results.append(selected)
        print('TRACK',track['receiver'],len(rows),round(track['span_s'],1),selected['catalog_number'],
              round(selected['shape_rms_hz'],1),selected['offset_s'],flush=True)
    return results


def run(directory):
    started = time.monotonic()
    data = load(directory)
    output = directory/'bootstrap.json'
    if output.exists():
        raise FileExistsError(output)
    tracks, receipt = reconstruct(data, directory)
    if not tracks:
        raise ValueError('no supported bootstrap tracks; do not invent calibration')
    matches = identify_tracks(data, tracks)
    accepted = [r for r in matches if r['accepted']]
    if {r['receiver'] for r in accepted} != {0,1}:
        raise ValueError('bootstrap lacks support on both receivers')
    # Receiver offsets/slopes are shared across satellite tracks, unlike the free
    # per-track constants used to rank shapes above. Five common timing starts
    # reproduce the original initialization strategy.
    from staged_fit import fit_receiver_lines
    from prepare_scans import ShiftedData
    from track_seed import loss
    rough = dict(position_km=data.initial[:2], assignments=accepted)
    attempts = []
    for offset in (-10.,-5.,0.,5.,10.):
        parameters = fit_receiver_lines(ShiftedData(data,offset),rough)
        parameters[6:] = offset
        costs = []
        for track in accepted:
            rows = np.asarray(track['rows'],int)
            prediction, visible = data.predict(parameters,rows=rows,satellites=np.full(len(rows),track['satellite_index']))
            residual = circular(data.measured[rows]-prediction)
            if np.any(visible):
                costs.append(float(np.mean(loss(residual[visible]))))
        attempts.append(dict(common_shift_s=offset, parameters=parameters.tolist(), score=float(np.mean(costs))))
    chosen = min(attempts,key=lambda r:r['score'])
    output_data = dict(status='initialized_not_validated', tracks=matches, trajectory=receipt,
                       initial_parameters=chosen['parameters'], common_timing_trials=attempts,
                       selected_seed_numbers=sorted({r['catalog_number'] for r in accepted}),
                       original_rows=data.original_rows.tolist(), elapsed_s=time.monotonic()-started,
                       sources={**data.sources,str(Path(__file__)):digest(Path(__file__).read_bytes())},
                       scope=__doc__, note='The <=24 long tracks initialize nuisance parameters only; exhaustive discovery still tests the full visible bank.')
    with output.open('x') as stream:
        json.dump(output_data,stream,indent=2,allow_nan=False)
    print(json.dumps(dict(status=output_data['status'], tracks=len(matches),
                          seed_satellites=len(output_data['selected_seed_numbers']), elapsed_s=output_data['elapsed_s'])),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args = parser.parse_args()
    run(args.directory)
