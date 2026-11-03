"""Bounded public-port export of an explicitly inspected original graph curve."""

import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
from run_algo01_ds23_sample import ROOT,DATASET,OUT as SOURCE,read,sha
from leo.analysis.glrt_frequency_input import frequency_evidence
from leo.storage.short_window import ShortWindowReader


def run(case,key):
    member=next(m for m in read(DATASET/'manifest.json')['members'] if m['dataset_label']==case)
    if member['recording_format']!='short_window_iq_recording':raise ValueError('existing public short-window port required')
    document=read(SOURCE/case/'tracking.json');evidence,_,_=frequency_evidence(document)
    lookup={'sha256:'+hashlib.sha256(identity.encode()).hexdigest():p for identity,p in zip(evidence.ids,document['source']['probes'],strict=True)}
    track=next(t for t in read(SOURCE/case/'tracks.json') if t['key']==key)
    if not 8<=len(track['observation_ids'])<=96:raise ValueError('bounded complete graph curve required')
    required={}
    for oid in track['observation_ids']:
        p=lookup[oid]
        if p['visit_index']>=1024:raise ValueError('early-read budget exceeded')
        peak=max((c for c in p['candidates'] if c['passed_fractional_margin_gate']),key=lambda c:(c['fractional_margin'],-c['candidate_rank']))
        required.setdefault(p['visit_index'],[]).append(dict(observation_id=oid,track_key=key,visit_index=p['visit_index'],
            receiver_id=p['receiver_id'],channel=p['channel'],edge=p['edge'],rf_hz=p['actual_rf_hz'],
            sample_counter=p['valid_start_counter'],peak=peak,all_public_candidates=p['candidates']))
    arrays={};points=[];manifests=[];visited=0
    for authority in member['raw_recording']['segments']:
        path=Path(authority['path']);assert 'sha256:'+sha(path)==authority['sha256']
        reader=ShortWindowReader(path.parent);manifests.append(dict(path=str(path),sha256=sha(path)))
        for window in reader.windows():
            visited+=1;visit=window.index.acquisition['global_visit']
            if visit in required:
                name=f'window_{visit:06d}';arrays[name]=np.array(window.samples,copy=True)
                for p in required[visit]:
                    assert window.index.acquisition['sample_start']==p['sample_counter']
                    points.append(dict(p,window_key=name,receiver_offset=reader.manifest.receiver_ids.index(p['receiver_id']),raw_window_sha256=window.index.iq_sha256))
            if visited>=1024 or len(points)==len(track['observation_ids']):break
        if visited>=1024 or len(points)==len(track['observation_ids']):break
    assert len(points)==len({p['observation_id'] for p in points})==len(track['observation_ids'])
    metadata=dict(case=case,sample_rate_hz=document['source']['sample_rate_hz'],points=points,tracks=[track],
        source_sha256=sha(Path(__file__)),tracking_sha256=sha(SOURCE/case/'tracking.json'),tracks_sha256=sha(SOURCE/case/'tracks.json'),
        reader_source_sha256=sha(ROOT/'src/leo/storage/short_window.py'),recording_manifests=manifests,
        raw_windows_read=visited,max_raw_windows=1024,all_selected_track_points_exported=True,
        selection='explicit originally nominated companion; targeted diagnostic, no GPS/error selection')
    arrays['metadata_json']=np.array(json.dumps(metadata));np.savez_compressed(sys.stdout.buffer,**arrays)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True);parser.add_argument('--track-key',required=True)
    args=parser.parse_args();run(args.case,args.track_key)
