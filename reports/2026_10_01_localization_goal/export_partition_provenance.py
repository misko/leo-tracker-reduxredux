"""Read cached detector provenance through the pinned production public input port."""
import argparse
import hashlib
import json
from pathlib import Path

from leo.analysis.persistent_hop_trajectory import (
    PersistentHopTrajectoryConfig,
    reconstruct_persistent_hop_trajectories,
)
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

HERE = Path(__file__).resolve().parent


def digest(path):
    return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--units', nargs='+', required=True)
    args = parser.parse_args()
    selection = HERE/'student-scale-expansion-v1-freeze.json'
    assert digest(selection) == selection.with_suffix('.sha256').read_text().strip()
    planned = json.loads(selection.read_text())['ordered_units']
    units = args.units
    assert len(set(units)) == len(units) and set(units) <= set(planned)
    store = ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    rows = []
    try:
        for unit in units:
            parent_path = next((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
            seal = json.loads(parent_path.with_suffix('.seal.json').read_text())
            assert digest(parent_path) == seal['prediction_sha256']
            parent = json.loads(parent_path.read_text())
            candidates = [Path(p) for p in parent['inputs'] if p.endswith('observations.json')]
            assert len(candidates) == 1
            source_path = candidates[0]
            assert digest(source_path) == parent['inputs'][str(source_path)]
            expected = json.loads(source_path.read_text())
            try:
                raw = store.load(expected['session_id'])
                if raw.input_manifest_sha256 != expected['manifest_sha256']:
                    raise ValueError('capture manifest differs from frozen export')
                if raw.analysis_manifest_sha256 != expected['analysis_manifest_sha256']:
                    raise ValueError('analysis manifest differs from frozen export')
                points = project_scanner_candidates(raw)
                by_id = {p.candidate_id: p for p in points}
                graph = reconstruct_persistent_hop_trajectories(
                    points, config=PersistentHopTrajectoryConfig(
                        minimum_span_s=3., minimum_support=6))
                tracks = {t.tracklet_id: t for t in graph.tracklets}
                evidence = []
                for track in expected['tracks']:
                    actual = tracks[track['track_id']]
                    members = [by_id[p.candidate_id] for p in actual.points]
                    assert [p.visit_index for p in members] == track['visits']
                    times = [(p.support_center_utc_ns-expected['start_utc_ns'])/1e9
                             for p in members]
                    pairs = zip(times, track['times_s'], strict=True)
                    assert max(abs(a-b) for a, b in pairs) < 1e-9
                    for p, measured in zip(members, track['measured_hz'], strict=True):
                        alias = (measured*p.actual_rf_hz/11.2e9-p.measured_cfo_hz)*4.4e-6
                        assert abs(alias-round(alias)) < 1e-8
                    fields = ['candidate_id', 'source_group_id', 'candidate_rank', 'probe_index',
                              'visit_index', 'receiver_id', 'channel', 'actual_rf_hz',
                              'source_sample_start', 'source_sample_end',
                              'support_start_utc_ns', 'support_center_utc_ns', 'support_end_utc_ns',
                              'measured_cfo_hz', 'standard_uncertainty_hz', 'exact_score',
                              'control_score', 'margin']
                    evidence.append(dict(
                        track_id=track['track_id'],
                        points=[{k: getattr(p, k) for k in fields} for p in members]))
                rows.append(dict(unit=unit, status='bound', observation_sha256=digest(source_path),
                                 session_id=raw.session_id,
                                 input_manifest_sha256=raw.input_manifest_sha256,
                                 analysis_manifest_sha256=raw.analysis_manifest_sha256,
                                 sample_rate_hz=raw.sample_rate_hz, probe_ms=raw.probe_ms,
                                 qualified=raw.qualified, tracks=evidence))
            except (AssertionError, KeyError, ValueError, OSError) as error:
                rows.append(dict(unit=unit, status='not_bound',
                                 observation_sha256=digest(source_path),
                                 error=type(error).__name__+': '+str(error)))
    finally:
        store.close()
    import sys
    sources = {}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename and ('/src/leo/' in filename or filename == __file__):
            path = Path(filename)
            if path.is_file() and path.suffix == '.py':
                sources[str(path.resolve())] = digest(path)
    result = dict(rows=rows, source_sha256=sources, selection_sha256=digest(selection),
                  qualification='Read cached public detector projection; no IQ reads, new RF, '
                  'model fitting or store writes. Exact capture/analysis/track/time/visit binding. '
                  'These are detection scores and CFO support metadata, not decoded satellite IDs.')
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(dict(output=str(args.output), sha256=digest(args.output),
                          rows=[{k: v for k, v in r.items() if k != 'tracks'} for r in rows])))


if __name__ == '__main__':
    main()
