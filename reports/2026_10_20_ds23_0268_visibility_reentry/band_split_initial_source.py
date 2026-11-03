"""Waveform-consistent alternative: retain RX1 CH1 with the RX2 family.

The raw overlap suggests a common transmitted component, not a unique NORAD.
Test whether the long RX1 high-band curve and CH2 curve can instead form the
67953 family, without moving the disputed CH1 curve away from RX2's 53923.
"""

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor
import numpy as np

from algo02_scan import pair_passes
from debug_ds23_0268_visibility_reentry import OUT,apply_nominations
from investigate_ds23_0268_remaining_tracks import load,fine_receiver_basis,OUT as PREVIOUS
from investigate_ds23_adaptive_failures import phase_widths
from probe_algo03_frame_peak_recovery import context
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_frequency_events import refit
from probe_ds23_0268_selected_identity_split import constrained_job
from run_algo01_ds23_sample import ROOT,read,write,sha

NAMES=('band_split_CH5_CH2_L0_H0','band_split_CH5_CH2_L0_H1',
       'band_split_CH5_CH2_L1_H0','band_split_CH5_CH2_L1_H1')


def job(name):
    destination=OUT/(name+'.json')
    if destination.exists():raise FileExistsError('preserve band identity trial')
    scan,base,saved,_,_=load()
    selected_path=OUT/'trials/interior_add_66797.json'
    selected=read(selected_path)
    old=context('DS23-0268')[4]
    replacements=[(r['component'],67953,None) for r in base.rows if 'RX1-CH5-T003' in r['component']]
    row=next(r for r in read(PREVIOUS/'causal_refined.json')['arms']['c0'] if 'RX1-CH2-T005' in r['component'])
    best=next(r['best'] for r in row['refined'] if r['best']['norad']==67953)
    replacements.append((row['component'],67953,best['alias']))
    node,mask,changes=apply_nominations(scan,selected['node'],base,selected['mask'],['RX1-CH2-T005'],replacements)
    entries=copy.deepcopy(old['linear_entries'])
    for entry in entries:
        t=scan.tracks[entry['track_index']]
        if entry['norad']!=53923 or t['receiver']!=1:continue
        if ('_L1_' in name and t['channel']<=4) or (name.endswith('_H1') and t['channel']>4):
            entry.update(norad=67953,candidate_index=int(np.flatnonzero(scan.norads==67953)[0]))
    changed=copy.copy(scan)
    changed.rx_basis=[fine_receiver_basis(t['times']) for t in scan.tracks]
    model=old['hyperparameters_from_pre_RF_TLE_only']
    labels=sorted({r['candidate_index'] for r in node['seed']['rows']})
    _,receipts=phase_widths(scan,labels)
    means=forecast_phase_mean(receipts,model['shrinkage'])
    arms={a:refit(changed,node,mask,a,np.asarray(selected['powers']),means,model,saved['events'],entries)
          for a in ('c0','fitted_c')}
    result=dict(name=name,arms=arms,node=node,mask=mask,powers=selected['powers'],predictive_entries=entries,
        changes=changes,paired_valid=pair_passes(arms,include_linear=True),
        original_selected_observation_mask_retained=True,CH1_kept_with_original_RX2_family=True,
        additional_CH2_points=62,GPS_used=False,future_TLE_used=False,
        selected_source_sha256=sha(selected_path),source_sha256=sha(ROOT/'tools/probe_ds23_0268_band_identity_split.py'))
    write(destination,result)
    print(name,'paired valid',result['paired_valid'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage',choices=('fit','constrained'),default='fit')
    args=parser.parse_args()
    with ProcessPoolExecutor(max_workers=4) as pool:
        list(pool.map(job if args.stage=='fit' else constrained_job,NAMES))
