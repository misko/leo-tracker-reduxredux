"""Matched causal/following TLE phase profiles of the partial0028 suffix."""

from pathlib import Path

import numpy as np
from sgp4.api import Satrec

import repair_ds23_iteration009_targets as repair
import diagnose_ds23_iteration007_tracks as diagnostic
from diagnose_ds23_partial_curved_tail import data_for
from diagnose_ds23_iteration002_curves import phase_profile
from leo.sky.propagation import ElementSetCatalogue
from analyze_dsx01_fixed_site import ecef_states
from run_algo01_ds23_sample import read,write,sha

OUT=repair.runner.RAW/'partial_tail_following'


def main():
    repair.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve partial-following diagnosis')
    write(OUT/'protocol.json',dict(source_sha256=sha(Path(__file__)),cases=read(repair.runner.RAW/'protocol.json')['cases'],
        target_IDs_frozen_by_original_partial_mask=True,
        candidates='two highest-scoring causal nominees for each diagnosed partial block',
        same_original_RF_endpoint_causal_receiver_posterior_phase_grid_and_no_shape_modes=True,
        following_epochs_and_collections_must_both_be_after_scan_end_within48h=True,
        following_TLE_diagnostic_only_no_inference_or_identity_selection=True))
    for case in read(OUT/'protocol.json')['cases']:
        d=repair.engine.current_setup(case);saved=d['arms']['c0'];x=np.asarray(saved['endpoint_east_north_km'])
        p=repair.engine.baseline.build(d,'c0',saved['phase_reference']);targets=read(repair.runner.RAW/'partial_tail_diagnostic'/(case+'.json'))['rows'];rows=[]
        wanted={r['norad'] for t in targets for r in t['candidates'][:2]}
        future=diagnostic.following(d,wanted) if wanted else None
        if future:write(OUT/(case+'_following.json'),future)
        for t in targets:
            data=data_for(d,p,x,t['source_row'],np.asarray(t['indices'],int));candidates=[]
            for c in t['candidates'][:2]:
                j=c['candidate_index'];bank=dict(time_s=d['scan'].sky['time_s'],position_km=d['scan'].sky['position_km'][[j]],velocity_km_s=d['scan'].sky['velocity_km_s'][[j]])
                profiles=dict(causal=phase_profile(data,bank,x,c['aliases']));version=future['versions'].get(str(c['norad']))
                if version:
                    catalogue=ElementSetCatalogue((str(c['norad']),),(c['norad'],),(Satrec.twoline2rv(*version['lines']),))
                    pos,vel,good=ecef_states(catalogue,d['scan'].receipt['origin_utc_ns'],bank['time_s'])
                    if not good.all():raise ValueError('following-tail propagation failed')
                    profiles['following']=phase_profile(data,dict(bank,position_km=pos,velocity_km_s=vel),x,c['aliases'])
                candidates.append(dict(norad=c['norad'],candidate_index=j,profiles=profiles,real_following_element=version is not None))
            rows.append(dict(component=t['component'],times=t['times'],indices=t['indices'],observation_ids=t['observation_ids'],candidates=candidates))
        write(OUT/(case+'.json'),dict(case=case,rows=rows,no_following_TLE_used_for_any_position_or_association=True))
    write(OUT/'execution.json',dict(all_terminal=True))


if __name__=='__main__':main()
