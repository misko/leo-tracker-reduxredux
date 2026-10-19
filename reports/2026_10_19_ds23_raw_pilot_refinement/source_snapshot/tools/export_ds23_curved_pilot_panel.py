"""Export complete early graph curves through the verified recording read port."""

import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
from run_algo01_ds23_sample import ROOT,DATASET,OUT as SOURCE,read,sha
from localize_merged_track_catalogue import raw_curvature
from leo.analysis.glrt_frequency_input import frequency_evidence
from leo.storage.short_window import ShortWindowReader


def run(case):
    member=next(r for r in read(DATASET/'manifest.json')['members'] if r['dataset_label']==case)
    if member['recording_format']!='short_window_iq_recording':raise ValueError('requires existing short-window read port')
    document=read(SOURCE/case/'tracking.json');evidence,_,_=frequency_evidence(document)
    lookup={'sha256:'+hashlib.sha256(identity.encode()).hexdigest():p for identity,p in zip(evidence.ids,document['source']['probes'],strict=True)}
    candidates=[]
    for t in read(SOURCE/case/'tracks.json'):
        ids=t['observation_ids']
        if not 12<=len(ids)<=96 or not all(oid in lookup for oid in ids):continue
        if not raw_curvature(dict(times=np.array(t['times']),values=np.array(t['values']))):continue
        if max(lookup[oid]['visit_index'] for oid in ids)>=1024:continue
        candidates.append(t)
    selected=[]
    for group in sorted({(t['receiver'],int(t['channel']>4)) for t in candidates}):
        rows=[t for t in candidates if (t['receiver'],int(t['channel']>4))==group]
        selected.append(max(rows,key=lambda t:(len(t['observation_ids']),t['key'])))
    required={};points=[]
    for track in selected:
        for oid in track['observation_ids']:
            p=lookup[oid];eligible=[c for c in p['candidates'] if c['passed_fractional_margin_gate']]
            peak=max(eligible,key=lambda c:(c['fractional_margin'],-c['candidate_rank']))
            required.setdefault(p['visit_index'],[]).append(dict(observation_id=oid,track_key=track['key'],
                visit_index=p['visit_index'],receiver_id=p['receiver_id'],channel=p['channel'],edge=p['edge'],rf_hz=p['actual_rf_hz'],
                sample_counter=p['valid_start_counter'],peak=peak,all_public_candidates=p['candidates']))
    arrays={};manifests=[];visited=0
    for authority in member['raw_recording']['segments']:
        path=Path(authority['path']);assert 'sha256:'+sha(path)==authority['sha256']
        reader=ShortWindowReader(path.parent);manifests.append(dict(path=str(path),sha256=sha(path)))
        for window in reader.windows():
            visited+=1;visit=window.index.acquisition['global_visit']
            if visit in required:
                key=f'window_{visit:06d}';arrays[key]=np.array(window.samples,copy=True)
                for p in required[visit]:
                    assert window.index.acquisition['sample_start']==p['sample_counter']
                    p.update(window_key=key,receiver_offset=reader.manifest.receiver_ids.index(p['receiver_id']),raw_window_sha256=window.index.iq_sha256)
                    points.append(p)
            if visited>=1024 or len(points)==sum(len(v) for v in required.values()):break
        if visited>=1024 or len(points)==sum(len(v) for v in required.values()):break
    expected={oid for t in selected for oid in t['observation_ids']}
    assert len(points)==len(expected)==len({p['observation_id'] for p in points})
    assert {p['observation_id'] for p in points}==expected
    metadata=dict(case=case,sample_rate_hz=document['source']['sample_rate_hz'],points=points,tracks=selected,
        source_sha256=sha(Path(__file__)),tracking_sha256=sha(SOURCE/case/'tracking.json'),tracks_sha256=sha(SOURCE/case/'tracks.json'),
        reader_source_sha256=sha(ROOT/'src/leo/storage/short_window.py'),recording_manifests=manifests,
        raw_windows_read=visited,max_raw_windows=1024,unavailable_groups_are_not_substituted=True,
        selection='largest whole graph curve per RX/band; >=12 and <=96 points, original active curvature; all visits <1024',
        no_GPS_TLE_satellite_association_or_error_used_for_track_selection=True,all_selected_track_points_exported=True)
    arrays['metadata_json']=np.array(json.dumps(metadata));np.savez_compressed(sys.stdout.buffer,**arrays)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True);run(parser.parse_args().case)
