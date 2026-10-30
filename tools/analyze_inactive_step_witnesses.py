"""Evaluate descriptive cross-family step evidence without changing fits."""
import argparse,hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from independent_step_witness import search
from leo.analysis.research.retained_track_likelihood import profile,whitening
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def screen(raw,times):
    terms=profile(raw,np.zeros(len(raw)),*whitening(times),bias_sigma=300.)
    noise=batch_noise_screen(terms['innovations'],times)
    return dict(RMS_hz=float(terms['rms'][0]),bias_hz=float(terms['bias'][0]),residual_hz=terms['residual'][0],
        innovations_hz=terms['innovations'][0],noise={k:v[0].item() for k,v in noise.items()})


def run(args):
    source=args.source;pr=read(source/'protocol.json');results=[];hashes={}
    for job in pr['jobs']:
        path=source/(job['track_id']+'.json');hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();data=read(path)
        for arm in data['results']:
            target=arm['target'];times=np.asarray(target['times_s']);raw=np.asarray(target['residual_hz'])+target.get('profile_bias_hz',0.)
            before=screen(raw,times)
            # Locate the target's existing gate maximum for context only. It
            # does not choose the witness-search grid, time or amplitude.
            r=np.asarray(before['innovations_hz']);n=len(r);splits=np.arange(4,n-3)
            jump=np.cumsum(r)[splits-1]/splits-(r.sum()-np.cumsum(r)[splits-1])/(n-splits)
            z=abs(jump)/(max(np.std(r,ddof=1),75)*np.sqrt(1/splits+1/(n-splits)))
            split=int(splits[np.argmax(z)])
            gate=dict(maximum_step_z=float(z.max()),left_time_s=float(times[split-1]),right_time_s=float(times[split]),
                left_points=split,right_points=n-split,left_minus_right_mean_hz=float(jump[np.argmax(z)]))
            models=[]
            for scope in ('same_receiver','same_receiver_band','other_receiver'):
                for scaling in ('hz','fractional'):
                    model=search(arm['all_active_curves'],target,scope=scope,scaling=scaling)
                    if model['best']:
                        b=model['best'];prediction=b['predicted_target_amplitude_hz']*(times>=b['time_s'])
                        model['target_after_counterfactual']=screen(raw-prediction,times)
                    models.append(model)
            results.append(dict(job=job,arm=arm['arm'],target=target,before=before,target_gate_split=gate,models=models,
                all_active_curves=arm['all_active_curves'],target_excluded_from_fit=True,
                target_family_excluded_from_witness_votes=True,shared_calibration_not_independent_holdout=True))
            offered=[(m['scope'],m['scaling'],m['best']['time_s']) for m in models if m['supported_exploratory_proposal']]
            print(job['label'],arm['arm'],'step',round(gate['maximum_step_z'],3),'proposals',offered,flush=True)
    write(args.output,dict(results=results,source_hashes=hashes,no_position_refit=True,no_acceptance_changes=True,
        independent_holdout_validation=False,amplitude_prior_hz=150,assumed_noise_hz=150,
        affine_removed_per_witness=True,one_average_information_vote_per_family=True,
        search_grid_s=1,window_padding_s=10,minimum_points_each_side=4,minimum_independent_families=2,
        proposal_rule='positive search-adjusted gain and at least two same-sign family amplitudes above two posterior standard deviations; exploratory only'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('source','output'):parser.add_argument('--'+key,type=Path,required=True)
    run(parser.parse_args())
