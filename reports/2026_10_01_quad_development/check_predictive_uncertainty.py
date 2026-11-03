"""Replay frozen means through predeclared shape/leverage predictive controls."""
import fcntl
import json
from pathlib import Path
import numpy as np
from run_window import prepare_window
from screen_seed_prefix import sealed,digest
from regression_batch import verify_sources
from failure_composition_checks import process_ok
from check_receiver_curvature import save
from predictive_uncertainty import ARMS,setup,score
HERE=Path(__file__).resolve().parent


def main():
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        selection=sealed(HERE/'selection.json');inputs={str(HERE/'selection.json'):digest(HERE/'selection.json')};rows=[];parity=[]
        captures=[r for r in selection['captures'] if r['block_id'] in ('DS9-B02','DS10-B02','DS11-B02')]
        for capture in captures:
            unit=capture['unit_id'];root=HERE/'trajectory-transfer-v1'/unit
            for name in ('result.json','sources.json','launch.json'):
                p=root/name;inputs[str(p)]=digest(p)
            result=sealed(root/'result.json');freeze=sealed(root/'sources.json');assert process_ok(sealed(root/'launch.json'))
            verify_sources(freeze['source_sha256']);verify_sources(freeze['inputs'])
            obs=HERE/'prepared'/unit/'observations.json';inputs[str(obs)]=digest(obs)
            original=json.loads(obs.read_text());assert original['manifest_sha256']==capture['manifest_sha256']
            lookup={r['track_id']:r for r in original['tracks']}
            for track in result['tracks']:
                raw=lookup[track['track_id']];t=np.array(raw['times_s']);y=np.array(raw['measured_hz']);n=len(t)
                for fold in track['folds']:
                    train=(np.arange(n)%2==fold['fold']) if fold['split']=='alternating' else (np.arange(n)<n//2);held=~train
                    assert int(held.sum())==fold['held_points']
                    model=fold['model'];chosen=fold['mixture_selected'];robust=dict(fold['robust'],sigma=fold['sigma_hz'])
                    single=setup(model,t[train],y[train],t[held],'single')
                    policy=setup(model,t[train],y[train],t[held],'mixture') if chosen else single
                    control=setup(robust,t[train],y[train],t[held],'robust') if robust['converged'] else None
                    base=float(score(single,y[held],'gaussian_fixed').sum());policy_old=float(score(policy,y[held],'gaussian_fixed').sum())
                    np.testing.assert_allclose(base,fold['baseline_score'],atol=1e-5,rtol=1e-12)
                    np.testing.assert_allclose(policy_old,fold['baseline_score']+fold['selected_gain'],atol=1e-5,rtol=1e-12)
                    parity.append(abs(policy_old-(fold['baseline_score']+fold['selected_gain'])))
                    if control is not None:np.testing.assert_allclose(score(control,y[held],'t4_same_fixed').sum(),fold['robust_score'],atol=1e-5,rtol=1e-12)
                    arms={}
                    for arm in ARMS:
                        scores={};errors={}
                        for name,value in (('single',single),('policy',policy),('robust',control)):
                            if value is None:scores[name]=None;errors[name]='saved robust fit not converged';continue
                            try:scores[name]=float(score(value,y[held],arm).sum())
                            except ValueError as exc:scores[name]=None;errors[name]=str(exc)
                        arms[arm]=dict(scores=scores,errors=errors)
                    rows.append(dict(unit=unit,track_id=track['track_id'],split=fold['split'],fold=fold['fold'],sigma_hz=fold['sigma_hz'],
                        held_points=fold['held_points'],mixture_selected=chosen,arms=arms,
                        maximum_policy_leverage=float(np.max(policy['leverage'])) if policy['leverage'] is not None else None))
            print(unit,'complete',flush=True)
        sources={str(HERE/name):digest(HERE/name) for name in ('predictive_uncertainty.py','check_predictive_uncertainty.py','test_predictive_uncertainty.py','PREDICTIVE_UNCERTAINTY_PLAN.md')}
        verify_sources(inputs);verify_sources(sources)
        save(HERE/'predictive-uncertainty-v1.json',dict(rows=rows,maximum_fixed_gaussian_score_difference=max(parity),inputs=inputs,sources=sources,
            qualification='Frozen-mean conditional-design predictive ablations; no fitting, parameter selection or localization.'))


if __name__=='__main__':main()
