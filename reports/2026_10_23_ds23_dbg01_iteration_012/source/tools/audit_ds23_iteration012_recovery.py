"""Fresh density, covariance, gate and physical-membership replay for012 trials."""

from pathlib import Path
import numpy as np

import probe_ds23_iteration012_curve_recovery as study
from audit_ds23_family_cavity import density
from probe_ds23_frequency_events import summary
from probe_ds23_reentry_family_cavity import assert_curved_gate_replay,assert_linear_gate_replay
from leo.analysis.research.retained_track_likelihood import profile
from ds23_predictive_subsets import realize_predictive_subsets
from run_algo01_ds23_sample import read,write,sha


def check(d,kind,trial,label):
    rows=[]
    for arm,saved in trial['arms'].items():
        p=study.binding.paths.paths.build(d,kind,arm,saved['phase_reference']);x=np.asarray(saved['endpoint_east_north_km']);c=p.calculate(x)
        delta=c['negative_twice_elbo']-saved['negative_twice_elbo']
        if abs(delta)>1e-5:raise ValueError('012 trial objective no longer replays')
        audit=density(d,p,x,d['means'],d['entries']);gates=summary(p,x,d['entries'])
        assert_curved_gate_replay(saved['gates'],gates['gates'])
        for old,new,e,sl in zip(saved['linear_gates'],gates['linear_gates'],d['entries'],p.linear_slices,strict=True):
            raw=c['linear_raw_prediction_residual_hz'][sl];terms=profile(raw,np.zeros(len(raw)),*p.scan.white[e['track_index']],bias_sigma=300.)
            assert_linear_gate_replay(old,new,dict(rms_hz=float(terms['rms'][0]),bias_hz=float(terms['bias'][0])))
        cov=study.core.coverage(d,kind,arm,saved) if label.startswith('core_') else study.binding.paths.paths.coverage(d,kind,arm,saved)
        if set(cov['accepted_observation_ids'])!=set(trial['coverage'][arm]['accepted_observation_ids']):raise ValueError('012 trial physical membership changed')
        rows.append(dict(case=d['scan'].case,method=label,arm=arm,accepted=trial['accepted'],objective_difference=delta,
            gates_and_unique_original_IDs_replayed=True,**audit))
    return rows


def main():
    study.configure('core');out=study.binding.runner.RAW/'recovery_endpoint_audit.json'
    if out.exists():raise FileExistsError('preserve012 recovery audit')
    rows=[]
    for case in read(study.binding.runner.RAW/'protocol.json')['cases']:
        d,cov,kind,_=study.core.parent.parent(case)
        folder=study.binding.runner.RAW/'graph_seeded_paths'
        for method,trial in read(folder/(case+'.json'))['methods'].items():
            if 'arms' not in trial:continue
            f=read(folder/(case+'_'+method+'_selection.json'))['selected']
            scan,entries=study.core.parent.native.append_native_paths(d['scan'],d['entries'],f,study.core.parent.native.receiver_basis(d['scan']))
            rows.extend(check(dict(d,scan=scan,entries=entries),kind,trial,'temporal_'+method))
        short=read(study.binding.runner.RAW/'short_whole_curves'/(case+'.json'))
        source=dict(d,original_protected=set(short['original_protected']));p=study.core.parent.build(source,kind,'c0',source['arms']['c0']['phase_reference'])
        for i,trial in enumerate(short['trials']):
            changed,_=study.short.promote(source,p,trial['offers']);rows.extend(check(changed,'support',trial,'short_'+str(i)))
        for trial in read(study.OUT/(case+'.json'))['trials']:
            offer=trial['offer'];p=study.core.parent.build(d,kind,'c0',d['arms']['c0']['phase_reference'])
            changed,entry,_=study.core.curved_core_view(d,p,offer['fragment'],offer['source_index'])
            if trial['method']=='core_predictive':
                scan,entries,_=realize_predictive_subsets(d['scan'],[dict(entry,track_index=offer['source_index'],component=offer['component'])]);changed=dict(d,scan=scan,entries=d['entries']+entries)
            rows.extend(check(changed,kind,trial,trial['method']))
    write(out,dict(rows=rows,all_passed=True,GPS_or_following_TLE_used=False,source_sha256=sha(Path(__file__))))
    print('Independently replayed012 recovery endpoint arms:',len(rows),flush=True)


if __name__=='__main__':main()
