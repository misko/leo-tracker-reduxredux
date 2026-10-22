"""Fresh native RF density/gate/membership checks for changed saved decisions."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import copy
import numpy as np

import probe_ds23_paired_replacement_evidence as policy
import probe_ds23_family_cavity_nominations as nominations
from run_ds23_reentry_family_cavity_full import signed_with_recorded_reference,repair_references
from ds23_frequency_events import make_event_problem,attach_event_predictive
from audit_ds23_family_cavity import density
from probe_ds23_family_cavity_position import unused_count
from ds23_family_cavity import unused_student_gap
from probe_ds23_reentry_family_cavity import assert_curved_gate_replay,assert_linear_gate_replay,archived_linear_gates
from probe_ds23_frequency_events import summary
from audit_ds23_algo01_coverage import retained_metrics
from evaluate_ds23_phase_refreshed import extend_associations
from dbg01_unassociated import ownership
from leo.analysis.research.retained_track_likelihood import profile
from run_algo01_ds23_sample import ROOT,read,write,sha


def original_data(case):
    original=nominations.context_signed
    nominations.context_signed=signed_with_recorded_reference
    try:return nominations.setup(case)
    finally:nominations.context_signed=original


def one(case):
    selection=next(r for r in read(policy.OUT/'RF_selection.json')['rows'] if r['case']==case)
    source=read(policy.SOURCE/(case+'.json'));d=original_data(case);records=[]
    best=source['trials'][selection['best_paired_trial_index']]
    baseline,_=repair_references(source['baseline_arms'],source)
    parent_obs_path=ROOT/'reports/2026_10_20_ds23_combined_recovery_full/protocol.json'
    observation_root=Path(read(parent_obs_path)['input_roots'][case]);observations=read(observation_root/case/'observations.json')
    allids={o['observation_id'] for o in observations};paired_gains={}
    for name,node,entries,means,arms in [('original_signed',source['baseline_node'],source['baseline_entries'],source['baseline_means'],baseline),
        ('published_challenger',best['node'],best['entries'],best['means'],best['arms'])]:
        for arm,saved in arms.items():
            p=make_event_problem(d['scan'],node,d['keep'],arm,np.asarray(saved['phase_reference']),d['powers'],np.asarray(means),d['model'],[])
            attach_event_predictive(p,entries,d['powers']);x=np.asarray(saved['endpoint_east_north_km']);c=p.calculate(x)
            if abs(c['negative_twice_elbo']-saved['negative_twice_elbo'])>1e-5:raise ValueError('saved endpoint no longer replays')
            independent=density(d,p,x,np.asarray(means),entries);replay=summary(p,x,entries)
            assert_curved_gate_replay(saved['gates'],replay['gates'])
            for old,new,entry,sl in zip(archived_linear_gates(saved,len(entries)),replay['linear_gates'],entries,getattr(p,'linear_slices',[]),strict=True):
                raw=c['linear_raw_prediction_residual_hz'][sl];terms=profile(raw,np.zeros(len(raw)),*p.scan.white[entry['track_index']],bias_sigma=300.)
                assert_linear_gate_replay(old,new,dict(rms_hz=float(terms['rms'][0]),bias_hz=float(terms['bias'][0])))
            corrected=c['negative_twice_elbo']-unused_count(p,entries)*unused_student_gap(d['model']['nu'])
            expected=source['baseline_corrected_loss'][arm] if name=='original_signed' else saved['corrected_selection_loss']
            if abs(corrected-expected)>1e-5:raise ValueError('corrected evidence did not replay')
            paired_gains[name,arm]=corrected
            extended=extend_associations(p,x,retained_metrics(p,x));lookup={t['key']:t for t in d['scan'].tracks}
            rows=[dict(r,observation_ids=r.get('observation_ids',lookup[r['component']]['observation_ids'])) for r in extended['tracks']]
            ids=ownership(rows)
            if not ids<=allids:raise ValueError('nonphysical membership')
            records.append(dict(case=case,configuration=name,arm=arm,negative_twice_elbo=c['negative_twice_elbo'],corrected_loss=corrected,
                saved_objective_difference=c['negative_twice_elbo']-saved['negative_twice_elbo'],original_all_GLRT=len(allids),
                associated=len(ids),associated_percent=100*len(ids)/len(allids),associated_fragments=sum(r['compatible'] for r in rows),
                accepted_observation_ids=sorted(ids),curved_likelihood_points=int(d['keep'].sum()),predictive_likelihood_points=sum(e['points'] for e in entries),**independent))
    gains={a:paired_gains['original_signed',a]-paired_gains['published_challenger',a] for a in ['c0','fitted_c']}
    if any(abs(gains[a]-selection['RF_gains'][a])>1e-5 for a in gains):raise ValueError('both-arm decision gains did not independently replay')
    return dict(case=case,rows=records,RF_gains=gains,all_passed=True,source_sha256=sha(policy.SOURCE/(case+'.json')))


def main():
    frozen=read(policy.OUT/'RF_selection.json');cases=[r['case'] for r in frozen['rows']
        if any(r['accepted'][m]!=r['accepted']['published_c0_positive'] for m in ['paired_positive','paired_2log2_margin'])]
    if (policy.OUT/'changed_endpoint_audit.json').exists():raise FileExistsError('preserve changed-endpoint audit')
    with ProcessPoolExecutor(max_workers=4) as pool:rows=list(pool.map(one,cases))
    write(policy.OUT/'changed_endpoint_audit.json',dict(cases=cases,rows=rows,all_passed=all(r['all_passed'] for r in rows),
        fresh_original_and_challenger_densities_and_original_gates_replayed=True,
        all_new_decisions_use_published_fits_no_reoptimization=True,source_sha256=sha(Path(__file__))))
    print('Changed saved configurations audited',cases,flush=True)


if __name__=='__main__':main()
