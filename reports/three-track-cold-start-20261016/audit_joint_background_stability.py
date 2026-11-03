import sys,json
from pathlib import Path
sys.argv=['audit','early_to_late','fitted-c','band_bias','2']
exec(open('/tmp/run_generic_joint_track_fold.py').read().split('# Verify analytic')[0])
results=[]
background=np.ones(len(obs.times_s),bool)
for _,rows,_ in target_sets:background[rows]=False
for fold in ['early_to_late','late_to_early']:
    states={}
    for variant in ['no_bias','band_bias']:
        suffix='_no_bias' if variant=='no_bias' else ''
        d=json.loads((root/f'generic_joint_{fold}_fitted-c{suffix}_pass2.json').read_text());assert d['audit']['accepted']
        base_all=SharedScanObjective(model.original,shift);base_all.score=base.score
        replay=FrozenBandBiasJoint(base_all,full_basis if variant=='band_bias' else np.zeros((len(obs.times_s),0)),bias_indices if variant=='band_bias' else [])
        ee=replay.evaluate_joint(np.array(d['fit']['vector']),np.array(d['fit']['nuisance']));t=ee[3];b=t.responsibilities.argmax(axis=1);p=t.responsibilities[np.arange(len(b)),b];a=p>t.clutter_probability
        states[variant]=(t,b,p,a)
    old,ob,op,oa=states['no_bias'];new,nb,np_,na=states['band_bias'];strong=background&oa&(op>=.9)
    lost=strong&~(na&(nb==ob));changed=background&oa&na&(ob!=nb)
    results.append(dict(fold=fold,background_count=int(background.sum()),strong_background_matches=int(strong.sum()),strong_background_same_identity_retained=int(np.sum(strong&na&(nb==ob))),strong_background_lost_or_changed=int(lost.sum()),all_background_association_identity_swaps=int(changed.sum()),lost_examples=[dict(row=int(i),time_s=float(obs.times_s[i]),receiver=int(obs.receiver[i]),channel=int(obs.channel[i]),old_satellite=nums[ob[i]],new_satellite=nums[nb[i]] if na[i] else None,old_probability=float(op[i]),new_probability=float(np_[i]),old_residual_hz=float(old.residual_hz[i,ob[i]]),new_residual_to_old_satellite_hz=float(new.residual_hz[i,ob[i]])) for i in np.flatnonzero(lost)]))
(root/'joint_background_stability.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
