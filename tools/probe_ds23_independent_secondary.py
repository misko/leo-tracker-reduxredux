"""Admit independently curved RX components without requiring shared noise.

Only existing phase families are used in this first control. No original CFO
is refined. The added curve has its measured marginal scatter and kappa zero.
"""

import argparse
import copy
from pathlib import Path
import numpy as np
import probe_ds23_new_curved_family as base
import audit_ds23_new_curved_family as audit
from ds23_frame_peak_recovery import measurement_id, polynomial_screen
from ds23_frequency_events import make_event_problem
from probe_ds23_sign_carrier_position import context_signed
from run_algo01_ds23_sample import ROOT, read, write, sha
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis, whitening

OUT = ROOT/'reports/2026_10_21_ds23_independent_secondary'
BULK = Path('/srv/bulk/leo/research/ds23-independent-secondary-20261021')
INVENTORY = ROOT/'reports/2026_10_21_ds23_independent_secondary_inventory/evaluation.json'


def selected():
    return [r for r in read(INVENTORY)['rows'] if r['active_curvature_evidence'] is not None
            and r['strong_gap_at_both_positions'] and r['existing_phase_coordinate']]


def prepare(case):
    scan,node,mask,powers,means,hyper,entries,signed,source = context_signed(case)
    p = make_event_problem(scan,node,mask,'c0',np.zeros(len(means)),powers,means,hyper,[])
    augmented = copy.copy(scan)
    for name in ['tracks','rx_basis','white','index']:
        setattr(augmented,name,list(getattr(scan,name)))
    augmented.fixed_window_noise = copy.deepcopy(scan.fixed_window_noise); noise=augmented.fixed_window_noise
    if noise['extra_parameter_BIC_gain'] <= 0:
        noise['per_observation_noise_sigma_hz']={o:scan.radio_sigma_hz for t in scan.tracks for o in t['observation_ids']}
        noise['extra_parameter_BIC_gain']=1.
    extra,anchors,covariance,metadata,family_powers=[],{},{},[],{}
    for proposal in [r for r in selected() if r['case']==case]:
        root=Path(proposal['source_bulk']); group=proposal['group'];role=proposal['role'];candidate=proposal['candidate_index']
        if sha(root/'evaluation.json')!=proposal['source_RF_sha256'] or sha(root/'catalogue'/(group+'.json'))!=proposal['source_catalogue_sha256']:
            raise ValueError('independent-secondary source changed')
        if candidate not in p.labels:
            raise ValueError('first independent-secondary control requires existing phase coordinate')
        protocol,rf=read(root/'protocol.json'),read(root/'evaluation.json')
        jobs={j['probe']:j for j in protocol['jobs'] if j['case']==case}
        rows={r['probe']:r for r in rf['rows'] if r['case']==case and r['status']=='complete' and r['two_components_qualified']}
        points=proposal['points'];t=np.array([r['time_s'] for r in points]);y=np.array([r['value'] for r in points]);cov=proposal['covariance']
        evidence=polynomial_screen(t,y,np.full(len(t),cov['marginal_sigma_hz']))
        if evidence is None:
            raise ValueError('independent secondary lost active curvature')
        rx,ch,frequency=jobs[points[0]['probe']]['lane'];ids=[]
        for point in points:
            job,row=jobs[point['probe']],rows[point['probe']]
            if abs(row['refined_'+role+'_value']-point['value'])>1e-8:
                raise ValueError('independent native RF value changed')
            ids.append(measurement_id(case,rx,ch,frequency,point['time_s'],dict(epoch=job[role]['epoch'],cfo=row[role+'_fit']['CFO_hz'])))
        key=group+'-independent_'+role;index=len(augmented.tracks)
        augmented.tracks.append(dict(key=key,receiver=rx,channel=ch,rf_hz=frequency,times=t,values=y,observation_ids=ids,
            pieces=[],indices=[],start_s=float(t[0]),end_s=float(t[-1]),bank='research',quality_status='independently_curved_secondary'))
        augmented.rx_basis.append(projected_receiver_basis(t));augmented.white.append(whitening(t))
        ix=np.searchsorted(scan.times,t)
        if np.any(ix>=len(scan.times)) or np.max(abs(scan.times[ix]-t))>1e-6:
            raise ValueError('independent secondary differs from original probe grid')
        augmented.index.append(ix);noise['per_observation_noise_sigma_hz'].update({o:cov['marginal_sigma_hz'] for o in ids})
        extra.append(dict(component=key,track_index=index,candidate_index=candidate,norad=proposal['norad'],alias=0,points=len(t),observation_ids=ids))
        anchors[key]=[r['anchor_flat_index'] for r in points];covariance[key]=cov
        supported=[powers[k] for k,(row,sl) in enumerate(zip(p.rows,p.slices,strict=True)) if row['candidate_index']==candidate and mask[sl].any()]
        family_powers[candidate]=min(supported) if supported else .2
        metadata.append(dict(group=group,norad=proposal['norad'],candidate_index=candidate,curvature=evidence,
            catalogue_gaps=proposal['catalogue_score_gaps'],original_common_error_rejection=proposal['original_rejection']))
    old_ids={o for t in scan.tracks for o in t['observation_ids']};new_ids=[o for e in extra for o in e['observation_ids']]
    if len(new_ids)!=len(set(new_ids)) or old_ids.intersection(new_ids):
        raise ValueError('independent RF observation duplicated')
    return dict(case=case,enriched=augmented,refined=scan,original_scan=scan,node=node,original_node=node,mask=mask,original_mask=mask,
        powers=powers,original_powers=powers,means=means,original_means=means,hyper=hyper,original_entries=entries,extra=extra,
        anchors=anchors,covariance=covariance,new_family_powers=family_powers,metadata=metadata,original_labels=p.labels,labels=p.labels,
        original_flat_count=len(mask),updates={},signed=signed,signed_source=source)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['run','audit'],required=True);args=parser.parse_args()
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True)
    workflow=dict(cases=sorted({r['case'] for r in selected()}),inventory_sha256=sha(INVENTORY),
        only_new_evidence='RF-supported independently curved secondary with strong all-catalogue proposal gap',
        original_CFO_values_and_all_original_priors_gates_and_observations_unchanged=True,new_phase_coordinates=False,
        independent_error_assumption_kappa=0.,secondary_sigma_from_its_RF_polynomial_scatter=True,
        independence_is_a_research_assumption_not_a_calibrated_joint_RF_density=True,
        no_GPS_or_new_RF_or_future_TLE=True,
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/probe_ds23_new_curved_family.py',
            ROOT/'tools/ds23_new_curved_family.py',ROOT/'tools/audit_ds23_new_curved_family.py']})
    path=OUT/'workflow_protocol.json'
    if path.exists() and read(path)!=workflow:raise ValueError('independent-secondary workflow changed')
    if not path.exists():write(path,workflow)
    base.OUT,base.BULK,base.INVENTORY,base.prepare=OUT,BULK,INVENTORY,prepare
    base.cases=lambda:workflow['cases'];audit.inference=base
    if args.stage=='run':base.main()
    else:audit.main()


if __name__=='__main__':main()
