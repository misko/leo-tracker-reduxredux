"""Reconstruct training-only trajectories from cached public detector inputs."""
import argparse
import hashlib
import inspect
import json
import resource
import time
from pathlib import Path

from leo.analysis.persistent_hop_trajectory import (
    PersistentHopTrajectoryConfig,
    reconstruct_persistent_hop_trajectories,
)
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from visit_split import checking_visits

import leo

HERE = Path(__file__).resolve().parent


def digest(path):
    return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    start = time.monotonic()
    parser = argparse.ArgumentParser()
    parser.add_argument('unit', choices=['DS9-F001', 'DS10-F056', 'DS11-F001'])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    package = Path(inspect.getfile(leo)).parent
    files = [*package.rglob('*.py'), Path(__file__), HERE/'visit_split.py']
    sources = {str(p.resolve()): digest(p) for p in files}
    parent_path = next((HERE/'regression-v1').glob('batch-*/'+args.unit+'.json'))
    parent_seal = json.loads(parent_path.with_suffix('.seal.json').read_text())
    assert digest(parent_path) == parent_seal['prediction_sha256']
    parent = json.loads(parent_path.read_text())
    path = Path(next(p for p in parent['inputs'] if p.endswith('observations.json')))
    assert digest(path) == parent['inputs'][str(path)]
    original = json.loads(path.read_text())
    store = ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:
        raw = store.load(original['session_id'])
        assert raw.input_manifest_sha256 == original['manifest_sha256']
        assert raw.analysis_manifest_sha256 == original['analysis_manifest_sha256']
        checks = checking_visits((p.channel, p.visit_index) for p in raw.probes)
        points = project_scanner_candidates(raw)
        training = tuple(p for p in points if (p.channel, p.visit_index) not in checks)
        checking = tuple(p for p in points if (p.channel, p.visit_index) in checks)
        train_groups = {p.source_group_id for p in training}
        check_groups = {p.source_group_id for p in checking}
        assert train_groups.isdisjoint(check_groups)
        graph = reconstruct_persistent_hop_trajectories(training,
            config=PersistentHopTrajectoryConfig(minimum_span_s=3., minimum_support=6))
        by_id = {p.candidate_id: p for p in training}
        tracks = []
        for track in graph.tracklets:
            members = [by_id[p.candidate_id] for p in track.points]
            tracks.append(dict(track_id=track.tracklet_id, receiver_id=track.lane_key[2],
                channel=track.lane_key[0], rf_hz=track.lane_key[3],
                times_s=[(p.support_center_utc_ns-original['start_utc_ns'])/1e9 for p in members],
                measured_hz=[p.normalized_dealiased_cfo_hz for p in track.points],
                visits=[p.visit_index for p in members],
                candidate_ids=[p.candidate_id for p in members],
                source_group_ids=[p.source_group_id for p in members]))
        fields = ['candidate_id', 'source_group_id', 'receiver_id', 'channel', 'visit_index',
                  'probe_index', 'actual_rf_hz', 'support_center_utc_ns', 'source_sample_start',
                  'source_sample_end', 'measured_cfo_hz', 'exact_score', 'control_score', 'margin']
        checking_rows = [{k: getattr(p, k) for k in fields} for p in checking]
        hypotheses = [dict(track_ids=list(h.tracklet_ids),
                           aggregate_weighted_support=h.aggregate_weighted_support)
                      for h in graph.hypotheses]
    finally:
        store.close()
    for filename, expected in sources.items():
        assert digest(filename) == expected
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result = dict(schema='localization-source-split/v1', unit=args.unit,
                  observation_sha256=digest(path), parent_sha256=digest(parent_path),
                  input_manifest_sha256=raw.input_manifest_sha256,
                  analysis_manifest_sha256=raw.analysis_manifest_sha256,
                  session_id=raw.session_id, start_utc_ns=original['start_utc_ns'],
                  checking_visits=sorted(checks), training_source_groups=sorted(train_groups),
                  checking_source_groups=sorted(check_groups),
                  training_candidates=len(training), checking_candidates=len(checking),
                  training_tracks=tracks, training_hypotheses=hypotheses,
                  checking_points=checking_rows, source_sha256=sources,
                  cpu_s=usage.ru_utime+usage.ru_stime, seconds=time.monotonic()-start,
                  qualification='One metadata-only split before trajectory reconstruction. '
                  'No checking candidates enter training graph. Checking detector candidates '
                  'retain all individually admitted alternatives; no checking paths or identities '
                  'selected. Same-recording noise/timing dependencies remain; this is not an '
                  'independent recording holdout. No GPS, RF collection, IQ reread or fitting. '
                  'Actual installed Python source tree hashed before and verified after export.')
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(dict(unit=args.unit, output=str(args.output), sha256=digest(args.output),
                          training_candidates=len(training), checking_candidates=len(checking),
                          training_tracks=len(tracks), seconds=result['seconds'])))


if __name__ == '__main__':
    main()
