"""Bounded read-side adapter exporting an existing-IQ diagnostic panel."""

import hashlib
import json
from pathlib import Path
import time
import sys

import numpy as np

from run_algo01_ds23_sample import DATASET, read, sha
from investigate_ds23_0268_longest_unassociated import SOURCE, OUT, CASE
from leo.analysis.glrt_frequency_input import frequency_evidence
from leo.storage.short_window import ShortWindowReader


def main(stdout=False):
    output=OUT/'raw_panel.npz'
    if output.exists() and output.stat().st_size:raise FileExistsError('preserve original-IQ panel')
    tracking=read(SOURCE/CASE/'tracking.json')
    evidence,_,_=frequency_evidence(tracking)
    lookup={'sha256:'+hashlib.sha256(identity.encode()).hexdigest():p
            for identity,p in zip(evidence.ids,tracking['source']['probes'],strict=True)}
    target=read(OUT/'target.json');tracks=read(SOURCE/CASE/'tracks.json')
    anchor=next(t for t in tracks if '-RX1-CH1-T004-' in t['key'])
    selected=[(target,oid) for oid in target['observation_ids']]
    selected += [(anchor,anchor['observation_ids'][i])
                 for i in np.unique(np.rint(np.linspace(0,len(anchor['times'])-1,8)).astype(int))]
    required={}
    for t,oid in selected:
        p=lookup[oid]
        if p['visit_index']>=3000:raise ValueError('bounded early window export exceeded')
        peak=max((c for c in p['candidates'] if c['passed_fractional_margin_gate']),
                 key=lambda c:(c['fractional_margin'],-c['candidate_rank']))
        required.setdefault(p['visit_index'],[]).append(dict(observation_id=oid,track_key=t['key'],
            receiver_id=p['receiver_id'],channel=p['channel'],edge=p['edge'],rf_hz=p['actual_rf_hz'],
            visit_index=p['visit_index'],sample_counter=p['valid_start_counter'],peak=peak,
            time_s=t['times'][t['observation_ids'].index(oid)]))
    write_plan=dict(case=CASE,planned_points=len(selected),target_points=len(target['times']),anchor_points=8,
                    maximum_raw_windows=3000,maximum_seconds=240,read_only_existing_IQ=True,
                    tracking_sha256=sha(SOURCE/CASE/'tracking.json'),source_sha256=sha(Path(__file__)))
    from run_algo01_ds23_sample import write
    if not stdout:write(OUT/'raw_panel_plan.json',write_plan)
    member=next(m for m in read(DATASET/'manifest.json')['members'] if m['dataset_label']==CASE)
    arrays={};points=[];manifests=[];visited=0;started=time.monotonic()
    for authority in member['raw_recording']['segments']:
        path=Path(authority['path']);assert 'sha256:'+sha(path)==authority['sha256']
        reader=ShortWindowReader(path.parent);manifests.append(dict(path=str(path),sha256=sha(path)))
        for window in reader.windows():
            visited+=1;visit=window.index.acquisition['global_visit']
            if visit in required:
                key=f'window_{visit:06d}';arrays[key]=np.array(window.samples,copy=True)
                for p in required[visit]:
                    assert window.index.acquisition['sample_start']==p['sample_counter']
                    points.append(dict(p,window_key=key,
                        receiver_offset=reader.manifest.receiver_ids.index(p['receiver_id']),
                        raw_window_sha256=window.index.iq_sha256))
            if len(points)==len(selected):break
            if visited>=3000 or time.monotonic()-started>240:
                raise RuntimeError('bounded existing-IQ read incomplete')
        if len(points)==len(selected):break
    assert len(points)==len({p['observation_id'] for p in points})==len(selected)
    metadata=dict(**write_plan,sample_rate_hz=tracking['source']['sample_rate_hz'],points=points,
                  recording_manifests=manifests,raw_windows_read=visited,seconds=time.monotonic()-started)
    arrays['metadata_json']=np.array(json.dumps(metadata))
    np.savez_compressed(sys.stdout.buffer if stdout else output,**arrays)
    if not stdout:
        write(OUT/'raw_panel_receipt.json',dict(points=len(points),seconds=time.monotonic()-started,
              panel_sha256=sha(output),raw_windows_read=visited))
    print('Exported existing IQ',len(points),'points in',time.monotonic()-started,'seconds',
          flush=True,file=sys.stderr)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--stdout',action='store_true')
    main(parser.parse_args().stdout)
