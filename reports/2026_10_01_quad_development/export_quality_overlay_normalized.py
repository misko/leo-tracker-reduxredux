"""Bounded read-only quality overlay; frozen observation exports remain unchanged."""
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
FIELDS = ('candidate_id', 'source_group_id', 'candidate_rank', 'receiver_id',
          'visit_index', 'probe_index', 'channel', 'actual_rf_hz',
          'support_start_utc_ns', 'support_center_utc_ns', 'support_end_utc_ns',
          'measured_cfo_hz', 'standard_uncertainty_hz', 'exact_score',
          'control_score', 'margin', 'factorial_support_moments_s')


def bind(document, projected):
    """Require a bijection to every frozen track/sample, preserving order."""
    for key in ('session_id', 'manifest_sha256', 'analysis_manifest_sha256', 'start_utc_ns'):
        if document[key] != projected[key]:
            raise ValueError('binding mismatch: ' + key)
    rows = projected['tracks']
    lookup = {r['track_id']: r for r in rows}
    if len(lookup) != len(rows):
        raise ValueError('duplicate projected track')
    seen = set()
    result = []
    for frozen in document['tracks']:
        track = lookup.get(frozen['track_id'])
        if track is None:
            raise ValueError('missing frozen track')
        points = track['points']
        if len(points) != len(frozen['times_s']):
            raise ValueError('sample count mismatch')
        for i, point in enumerate(points):
            cid = point['candidate_id']
            if cid in seen:
                raise ValueError('reused candidate')
            seen.add(cid)
            actual = (point['support_center_utc_ns'] - document['start_utc_ns']) / 1e9
            if actual != frozen['times_s'][i] or point['normalized_dealiased_cfo_hz'] != frozen['measured_hz'][i]:
                raise ValueError('time/frequency mismatch')
            if (point['visit_index'] != frozen['visits'][i]
                    or point['receiver_id'] != frozen['receiver_id']
                    or point['channel'] != frozen['channel']
                    or point['actual_rf_hz'] != frozen['rf_hz']):
                raise ValueError('physical identity mismatch')
        result.append(track)
    if len({r['track_id'] for r in result}) != len(result):
        raise ValueError('duplicate frozen track')
    return dict(tracks=result, matched_tracks=len(result), matched_samples=len(seen),
                extra_projected_tracks=len(lookup)-len(result))


def main():
    from prepare_block import verify_reader, RUNTIME, GOAL
    def digest(path):
        return 'sha256:' + hashlib.sha256(Path(path).read_bytes()).hexdigest()
    selection_path = HERE / 'selection.json'
    assert digest(selection_path) == selection_path.with_suffix('.sha256').read_text().strip()
    selection = json.loads(selection_path.read_text())
    out = HERE / 'quality-overlay-v3'
    with (GOAL / '.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        out.mkdir(exist_ok=False)
        before = verify_reader()
        code = '''
import json,sys
from pathlib import Path
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.analysis.persistent_hop_trajectory import PersistentHopTrajectoryConfig,reconstruct_persistent_hop_trajectories
store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
try:
 raw=store.load(sys.argv[1])
 points=project_scanner_candidates(raw)
 by_id={p.candidate_id:p for p in points}
 assert len(by_id)==len(points)
 graph=reconstruct_persistent_hop_trajectories(points,config=PersistentHopTrajectoryConfig(minimum_span_s=3.,minimum_support=6))
 fields=json.loads(sys.argv[2])
 tracks=[dict(track_id=t.tracklet_id,points=[dict({k:getattr(by_id[p.candidate_id],k) for k in fields}, normalized_dealiased_cfo_hz=p.normalized_dealiased_cfo_hz) for p in t.points]) for t in graph.tracklets]
 print(json.dumps(dict(session_id=sys.argv[1],manifest_sha256=raw.input_manifest_sha256,analysis_manifest_sha256=raw.analysis_manifest_sha256,start_utc_ns=raw.timing.first_sample_estimate_utc_ns,tracks=tracks),allow_nan=False))
finally: store.close()
'''
        results = []
        for dataset in ('DS9', 'DS10', 'DS11'):
            capture = next(r for r in selection['captures'] if r['block_id'] == dataset+'-B01')
            unit = capture['unit_id']
            path = HERE / 'prepared' / unit / 'observations.json'
            frozen = json.loads(path.read_text())
            assert frozen['session_id'] == capture['session_id']
            assert frozen['manifest_sha256'] == capture['manifest_sha256']
            started = time.monotonic()
            call = subprocess.run(['sudo', '-n', '-u', 'leo', 'env',
                'OPENBLAS_NUM_THREADS=1', 'OMP_NUM_THREADS=1', 'MKL_NUM_THREADS=1',
                'timeout', '--kill-after=2s', '85s', RUNTIME, '-c', code,
                frozen['session_id'], json.dumps(FIELDS)], capture_output=True,
                text=True, timeout=90)
            record = dict(unit=unit, returncode=call.returncode, seconds=time.monotonic()-started,
                          observation_path=str(path), observation_sha256=digest(path))
            if call.returncode:
                record.update(status='export_failed', stderr=call.stderr)
            else:
                try:
                    record.update(bind(frozen, json.loads(call.stdout)), status='bound')
                except (ValueError, KeyError) as exc:
                    record.update(status='binding_failed', reason=str(exc))
            results.append(record)
            print(json.dumps({k:v for k,v in record.items() if k != 'tracks'}), flush=True)
        after = verify_reader()
        result = dict(results=results, reader_before=before, reader_after=after,
            inputs={str(selection_path):digest(selection_path)},
            sources={str(Path(__file__).resolve()):digest(__file__)},
            qualification='Quality overlay only; heuristic uncertainty is not calibrated measurement variance. No fits or IQ reads.')
        target = out / 'overlay.json'
        with target.open('x') as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
        target.with_suffix('.sha256').write_text(digest(target)+'\n')


if __name__ == '__main__':
    main()

