"""Compare proposal screens at the identical graph parent; no new position fit."""

from pathlib import Path
import numpy as np

import probe_ds23_iteration015_joint_phase_alias as study
from ds23_family_cavity import coarse_phase_scores
from probe_ds23_single_curved_reentry import predictive_track_data
from probe_ds23_family_cavity_nominations import candidate_prediction
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import read,write,sha


def main():
    out=study.OUT/'linearized_matched_control.json'
    if out.exists():raise FileExistsError('preserve matched proposal control')
    study.binding.configure('paths');rows=[]
    for case in read(study.runner.RAW/'protocol.json')['cases']:
        result=read(study.OUT/(case+'.json'))
        if not result['targets']:continue
        d,cov,kind,_=study.paths.parent(case);s=d['arms']['c0'];x=np.asarray(s['endpoint_east_north_km']);p=study.paths.build(d,kind,'c0',s['phase_reference'])
        for target in result['targets']:
            row=p.members.index(target['track_index']);data=predictive_track_data(d,p,x,row);f,e=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(x),phase_seconds=d['all_means'])
            plus=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(x),phase_seconds=d['all_means']+.01)[0];minus=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(x),phase_seconds=d['all_means']-.01)[0]
            coarse=coarse_phase_scores(data['values'],data['radio']@data['coefficient'][:data['radio_width']],f*data['q'],(plus-minus)/.02*data['q'],d['widths'],data['base_covariance'],data['groups'])
            score=np.where(np.min(e,axis=1)>=0,coarse['score'],np.inf);pool=[int(j) for j in np.argsort(score) if np.isfinite(score[j])][:7]
            for old in [target['original_nomination_best'],target['nominal_original']]:
                if old is not None and old['candidate_index'] not in pool:pool.append(old['candidate_index'])
            nominees=sorted([candidate_prediction(dict(d,x=x),data,j,coarse['aliases'][j]) for j in pool],key=lambda r:r['score']);checks=[]
            for a in nominees:
                b=next((r for r in target['candidates'] if r['candidate_index']==a['candidate_index'] and r['aliases']==a['aliases']),None)
                if b is not None:
                    delta=a['score']-b['score']
                    if abs(delta)>1e-8:raise ValueError('common proposal differs despite identical parent and alias')
                    checks.append(dict(norad=a['norad'],score_difference=delta))
            rows.append(dict(case=case,component=target['component'],same_graph_parent_position_radio_mask_priors_and_candidate_refiner=True,
                linearized_candidates=nominees,nonlinear_candidates=target['candidates'],common_score_checks=checks,
                linearized_best=next((r['norad'] for r in nominees if r['qualified']),None),
                nonlinear_best=next((r['norad'] for r in target['candidates'] if r['qualified']),None)))
    write(out,dict(rows=rows,all_common_scores_match=True,no_new_fit_or_GPS=True,source_sha256=sha(Path(__file__))))
    print([(r['case'],r['linearized_best'],r['nonlinear_best']) for r in rows],flush=True)


if __name__=='__main__':main()
