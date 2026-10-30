"""Train a single exact family phase, then transfer it to withheld scan blocks.

The native identity and graph are frozen prior hypotheses. This is conditional
model validation, not independent satellite identity validation. No held values
enter calibration, phase selection, constant fitting or grid construction.
"""
import argparse
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from native_predictive_branch import native_context,validated_native_source
from annotate_track_predictively import fit_training
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from investigate_ds23_0268_remaining_tracks import family_frequency
from probe_shared_phase_feasibility import fixed_alias_constant,constant_scale
from leo.analysis.research.grouped_prediction import replay_split


def run(args):
    out=args.output;out.mkdir(exist_ok=False,parents=True)
    pr=read(args.diagnostic/'protocol.json');inv=read(Path(pr['inventory']));d=context(inv)
    source=validated_native_source(Path(pr['validation']));target=pr['target'];j=target['candidate_index']
    d,_=native_context(d,inv,source,target['component'].split('-NATIVE-')[-1])
    annotation=read(Path(pr['validation'])/'result.json');folds=[]
    write(out/'protocol.json',dict(source_protocol=pr,randomized_scanwide_blocks=True,block_s=12,guard_s=2,
        seeds=[f['seed'] for f in annotation['folds']],matched_c=True,GPS_used=False,future_TLE=False,
        all_calibration_and_phase_fitting_training_only=True,position_and_receiver_frozen_after_training_calibration=True,
        conditional_on_previously_selected_identity_and_graph=True,independent_identity_validation=False,
        phase_grid='[-15,15] step .1 plus +/-1 around training endpoint step .002 seconds',
        original_curved_training_noise_hz=150,predictive_target_noise_variance_hz2=2*150**2,
        constant_prior_sigma_hz=300,score='conditional MAP with frozen training Gamma precisions',
        predictive_uncertainty_not_integrated=True,no_accepted_associations=True))
    p0,_=d['problems']['c0']
    for fold in annotation['folds']:
        train,held=replay_split(p0.flat_times,fold['split']);arms={}
        for arm in ('c0','fitted_c'):
            p,x,meta=fit_training(d,d['node'],d['keep']&train,arm);c=p.calculate(x)
            begin=p.hardware.shape[1]+p.smooth.shape[1];local=p.labels.index(j);pi=begin+local
            const=begin+len(p.labels)+3*len(p.supported);original=p.calculate
            phi=float(c['coefficient'][pi]*p.phase_sigma[local]);curves=[]
            for k,(r,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
                if r['candidate_index']!=j:continue
                tr=p.keep[sl];he=d['keep'][sl]&held[sl]
                if tr.sum()<4:continue
                t=p.scan.tracks[i]
                curves.append(dict(component=t['key'],kind='existing',times_s=t['times'],
                    train=tr,held=he,q=t['rf_hz']/11.5e9,
                    raw=p.values[sl]-c['features'][sl,:begin]@c['coefficient'][:begin],
                    weight=np.full(len(t['times']),c['noise_precision'][k]/150**2),
                    prior_precision=float(c['coefficient_prior_precision'][const+k]/constant_scale(p,k)**2)))
            view,values,_,_,_=linear_geometry(p,[target]);g=geometry_features(view,x,0.)
            t=p.scan.tracks[target['track_index']];tr,he=replay_split(t['times'],fold['split'])
            if tr.sum()<8 or he.sum()<4:raise ValueError('insufficient native partition')
            curves.append(dict(component=target['component'],kind='target',times_s=t['times'],train=tr,held=he,
                q=t['rf_hz']/11.5e9,raw=values-g['features'][:,:begin]@c['coefficient'][:begin],
                weight=np.full(len(t['times']),1/(2*150**2)),prior_precision=1/300**2))
            def evaluate(phase,detail=False):
                coef=c['coefficient'].copy();coef[pi]=phase/p.phase_sigma[local]
                p.calculate=lambda _:dict(c,coefficient=coef)
                phase_cost=float(c['coefficient_prior_precision'][pi]*(coef[pi]-d['means'][local]/p.phase_sigma[local])**2)
                old_cost=phase_cost;target_cost=0.;rows=[]
                try:
                    for curve in curves:
                        f,_=family_frequency(p,x,j,times=curve['times_s']);raw=curve['raw']-curve['q']*f
                        tr,he=curve['train'],curve['held']
                        fit=fixed_alias_constant(raw[tr],curve['weight'][tr],curve['prior_precision'])
                        if curve['kind']=='target':target_cost+=fit['cost']
                        else:old_cost+=fit['cost']
                        if detail:
                            residual=raw[he]-fit['bias_hz']
                            rows.append(dict(component=curve['component'],kind=curve['kind'],train_points=int(tr.sum()),
                                held_points=int(he.sum()),times_s=curve['times_s'][he],residual_hz=residual,
                                RMS_hz=float(np.sqrt(np.mean(residual**2))) if len(residual) else None,
                                training_bias_hz=fit['bias_hz'],training_cost=fit['cost']))
                    return dict(phase_s=float(phase),old_cost=old_cost,joint_cost=old_cost+target_cost,curves=rows)
                finally:p.calculate=original
            grid=np.unique(np.round(np.r_[np.arange(-15,15.0001,.1),phi+np.arange(-1,1.0001,.002),phi],10))
            grid=grid[(grid>=-15)&(grid<=15)];costs=[evaluate(q) for q in grid]
            selected={name:evaluate(grid[int(np.argmin([v[key] for v in costs]))],True)
                for name,key in [('existing_only','old_cost'),('existing_plus_native','joint_cost')]}
            selected['original_phase']=evaluate(phi,True)
            arms[arm]=dict(training=meta,variants=selected,grid_phase_s=grid,
                grid_old_cost=[v['old_cost'] for v in costs],grid_joint_cost=[v['joint_cost'] for v in costs])
            print(fold['seed'],arm,[(k,round(v['phase_s'],4),round(v['curves'][-1]['RMS_hz'],2)) for k,v in selected.items()],flush=True)
        record=dict(seed=fold['seed'],split=fold['split'],arms=arms);folds.append(record);write(out/f"seed-{fold['seed']}.json",record)
    write(out/'result.json',dict(job=inv['job'],target=target,folds=folds,diagnostic_only=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--diagnostic',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);run(p.parse_args())
