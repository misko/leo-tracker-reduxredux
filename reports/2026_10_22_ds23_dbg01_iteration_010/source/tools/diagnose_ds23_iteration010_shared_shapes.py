"""RF-only curvature consistency across new graph additions and old families."""

from pathlib import Path
import numpy as np

import probe_ds23_iteration010_paths as binding
from ds23_receiver_curve_consistency import shared_shape
from run_algo01_ds23_sample import read,write,sha

OUT=binding.runner.RAW/'new_old_shared_shapes'


def main():
    binding.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve shared-shape diagnostic')
    cases=read(binding.runner.RAW/'protocol.json')['cases']
    write(OUT/'protocol.json',dict(cases=cases,source_sha256=sha(Path(__file__)),
        shared_helper_sha256=sha(Path(shared_shape.__code__.co_filename)),
        new_whole_graph_additions_versus_active_other_family_same_RX_components=True,
        minimum_actual_overlap_s=6,minimum_points_per_track=8,comparison_uses_whole_active_masks=True,
        independent_affine_terms_remove_alias_band_constants_and_linear_drift=True,
        diagnostic_only_no_TLE_GPS_or_identity_change=True))
    for case in cases:
        d,_,kind,selected=binding.paths.parent(case);rows=[]
        if selected:
            p=binding.paths.build(d,kind,'c0',d['arms']['c0']['phase_reference'])
            for addition in selected['additions']:
                track=next(t for t in d['scan'].tracks if t['key']==addition['component'])
                for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
                    old=d['scan'].tracks[i];use=p.keep[sl]
                    if row['candidate_index']==addition['candidate_index'] or old['receiver']!=track['receiver'] or use.sum()<8:continue
                    other=dict(old,times=old['times'][use],values=old['values'][use],observation_ids=np.asarray(old['observation_ids'])[use].tolist())
                    if min(other['times'][-1],track['times'][-1])-max(other['times'][0],track['times'][0])<6:continue
                    result=shared_shape([track,other],overlap_only=False)
                    rows.append(dict(new_component=track['key'],new_norad=addition['norad'],old_component=old['key'],old_norad=row['candidate_norad'],**result))
        write(OUT/(case+'.json'),dict(case=case,rows=sorted(rows,key=lambda r:r['BIC_shared_minus_independent']),no_inference_change=True))


if __name__=='__main__':main()
