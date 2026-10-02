"""Two-way alternating held-observation prediction on all pilot tracks."""
import fcntl
from pathlib import Path
import numpy as np
from run_window import prepare_window
from screen_seed_prefix import sealed,digest
from regression_batch import verify_sources
from check_receiver_curvature import save
from trajectory_mixture import fit,predict
HERE=Path(__file__).resolve().parent


def main():
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        path=HERE/'radio-segmentation-v1.json';data=sealed(path);verify_sources(data['sources']);verify_sources(data['inputs'])
        records=[]
        for scan in data['scans']:
            rows=[]
            for track in scan['tracks']:
                t=np.array(track['times_s']);y=np.array(track['frequencies_hz']);folds=[]
                for sigma in (100.,300.):
                    for parity in (0,1):
                        train=np.arange(len(t))%2==parity;held=~train
                        model=fit(t[train],y[train],sigma)
                        base=predict(model,t[held],y[held],single=True);mixture=predict(model,t[held],y[held])
                        improvement=2*(model['mixture_loglik']-model['single_loglik'])
                        select=model['status']=='mixture' and improvement>4*np.log(train.sum())
                        strict=model['status']=='mixture' and improvement>8*np.log(train.sum())
                        gain=float((mixture-base).sum())
                        folds.append(dict(sigma_hz=sigma,training_parity=parity,training_points=int(train.sum()),held_points=int(held.sum()),
                            model=model,mixture_selected=bool(select),double_penalty_selected=bool(strict),
                            baseline_log_score=float(base.sum()),raw_mixture_gain=gain,selected_gain=gain if select else 0.,
                            double_penalty_gain=gain if strict else 0.))
                rows.append(dict(track_id=track['track_id'],track_index=track['track_index'],samples=len(t),folds=folds))
            records.append(dict(unit=scan['unit'],tracks=rows));print(scan['unit'],len(rows),'complete',flush=True)
        sources={str(HERE/n):digest(HERE/n) for n in ('TRAJECTORY_MIXTURE_PLAN.md','trajectory_mixture.py','test_trajectory_mixture.py','check_trajectory_mixture.py')}
        verify_sources(sources)
        save(HERE/'trajectory-mixture-v1.json',dict(scans=records,inputs={str(path):digest(path)},sources=sources,
            qualification='Correlated alternating within-track held radio prediction; training-only model selection. Gaussian surrogate, no GPS, labels, localization fitting or original-input changes.'))


if __name__=='__main__':main()
