"""Read a bounded pilot panel through the verified short-window recording port.

Writes NPZ only to stdout; callers redirect to a local user-owned file.
No capture, raw recording mutation, or satellite/location input is used.
"""

import argparse
import json
import sys
from pathlib import Path
import numpy as np
from run_algo01_ds23_sample import ROOT,DATASET,OUT as SOURCE,read,sha
from leo.storage.short_window import ShortWindowReader


def eligible_peak(probe):
    candidates=[c for c in probe['candidates'] if c['passed_fractional_margin_gate'] and c['fractional_margin']>=.05 and 1000<abs(c['fractional_tracking_cfo_hz'])<399000]
    return max(candidates,key=lambda c:(c['fractional_margin'],-c['candidate_rank'])) if candidates else None


def run(case):
    dataset=read(DATASET/'manifest.json');member=next(r for r in dataset['members'] if r['dataset_label']==case)
    if member['recording_format']!='short_window_iq_recording':raise ValueError('this exporter requires the existing short-window read port')
    document=read(SOURCE/case/'tracking.json');source=document['source'];fs=source['sample_rate_hz']
    probes={}
    for p in source['probes']:
        key=(p['visit_index'],p['receiver_id'])
        if key in probes:raise ValueError('duplicate physical probe')
        probes[key]=p
    groups={(rx,band):0 for rx in sorted({p['receiver_id'] for p in source['probes']}) for band in (0,1)}
    arrays={};points=[];receipts=[];visited=0
    for authority in member['raw_recording']['segments']:
        path=Path(authority['path']);assert 'sha256:'+sha(path)==authority['sha256']
        reader=ShortWindowReader(path.parent);receipts.append(dict(manifest_path=str(path),sha256=sha(path)))
        for window in reader.windows():
            visited+=1;visit=window.index.acquisition['global_visit'];window_key=f'window_{visit:06d}';chosen=[]
            for offset,rx in enumerate(reader.manifest.receiver_ids):
                probe=probes.get((visit,rx))
                if probe is None:continue
                if window.index.acquisition['sample_start']!=probe['valid_start_counter']:raise ValueError('raw sample counter differs from public GLRT input')
                if probe['probe_start_ms']!=0 or len(window.samples)!=fs//50:raise ValueError('unsupported public probe support')
                group=(rx,int(probe['channel']>4));peak=eligible_peak(probe)
                if groups[group]>=2 or peak is None:continue
                groups[group]+=1;chosen.append(dict(window_key=window_key,receiver_offset=offset,receiver_id=rx,
                    visit_index=visit,channel=probe['channel'],edge=probe['edge'],rf_hz=probe['actual_rf_hz'],
                    sample_counter=probe['valid_start_counter'],peak=peak,all_public_candidates=probe['candidates'],
                    raw_window_sha256=window.index.iq_sha256))
            if chosen:arrays[window_key]=np.array(window.samples,copy=True);points.extend(chosen)
            if all(n==2 for n in groups.values()) or visited>=128:break
        if all(n==2 for n in groups.values()) or visited>=128:break
    metadata=dict(case=case,sample_rate_hz=fs,points=points,group_counts={f'RX{rx}/band{band}':n for (rx,band),n in groups.items()},
        raw_windows_read=visited,window_limit=128,points_per_RX_band=2,selection_uses_only_public_RF_peak_gate_margin_and_CFO_range=True,
        no_GPS_TLE_satellite_or_association_selection=True,tracking_sha256=sha(SOURCE/case/'tracking.json'),
        dataset_manifest_sha256=sha(DATASET/'manifest.json'),recording_manifests=receipts,
        source_sha256=sha(Path(__file__)),reader_source_sha256=sha(ROOT/'src/leo/storage/short_window.py'))
    arrays['metadata_json']=np.array(json.dumps(metadata));np.savez_compressed(sys.stdout.buffer,**arrays)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
