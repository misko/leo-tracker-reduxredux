"""Summarize saved audit evidence; no RF, calibration fitting, or GPS reads."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from audit import OUT, ROOT, TID
from leo.analysis.research.grouped_prediction import replay_split


def main():
    a=json.loads((OUT/'audit.json').read_text())
    assert a['completed']
    original=json.loads((ROOT/TID/'annotation/result.json').read_text())
    summary=dict(scope=a['scope'],seconds=a['seconds'],family=a['family'],baseline=a['baseline'],folds=[])
    fig,axes=plt.subplots(3,2,figsize=(14,12))
    counts=[]
    for k,fold in enumerate(a['folds']):
        times=np.asarray(a['family']['times_s']);ft,fh=replay_split(times,fold['split'])
        for arm,r in fold['arms'].items():
            ordered=sorted(r['held_66102'],key=lambda q:q['score']['negative_twice_log_density'])
            own=sorted(r['family_predictive_competitors'],key=lambda q:q['grouped']['score']['negative_twice_log_density'])
            inc=next(q for q in r['family_nominal_fits'] if q['norad']==52311)
            y=np.asarray(inc['corrected_observation_hz']);z=times-times.mean()
            affine=np.column_stack((np.ones(len(z)),z));linear_residual=y-affine@np.linalg.lstsq(affine,y,rcond=None)[0]
            quadratic=np.column_stack((np.ones(len(z)),z,z*z));coef=np.linalg.lstsq(quadratic,y,rcond=None)[0]
            old=next(q for q in original['folds'] if q['seed']==fold['seed'])['proposals'][0]['arms'][arm]
            counts.append(dict(seed=fold['seed'],arm=arm,training_points=fold['remaining_training_points'],
                excluded_training_points=fold['excluded_training_points']))
            row=dict(seed=fold['seed'],arm=arm,excluded_training_points=fold['excluded_training_points'],
                training_phase_change_s=r['training']['final_phase_change_s'],endpoint=r['training']['endpoint_east_north_km'],
                endpoint_change_from_original_fold_km=float(np.linalg.norm(np.asarray(r['training']['endpoint_east_north_km'])-old['endpoint_east_north_km'])),
                target66102_winner=ordered[0]['norad'],target66102_held_points=len(ordered[0]['score']['held_mean_hz']),
                target66102_held_rms_hz=ordered[0]['score']['rms_hz'],
                target66102_margin=ordered[1]['score']['negative_twice_log_density']-ordered[0]['score']['negative_twice_log_density'],
                family_winner=own[0]['norad'],family_runner_up=own[1]['norad'],family_held_points=int(fh.sum()),
                family_training_points=int(ft.sum()),family_held_rms_hz=own[0]['grouped']['score']['rms_hz'],
                family_margin=own[1]['grouped']['score']['negative_twice_log_density']-own[0]['grouped']['score']['negative_twice_log_density'],
                nominal52311_phase_s=inc['phase_s'],nominal52311_rms_hz=inc['rms_hz'],
                family_all_data_posterior_boundary_mass=own[0]['descriptive_all_data_boundary_mass'],
                affine_rms_hz=float(np.sqrt(np.mean(linear_residual**2))),quadratic_curvature_hz_s2=float(2*coef[2]),
                quadratic_rms_hz=float(np.sqrt(np.mean((y-quadratic@coef)**2))))
            summary['folds'].append(row)
            ax=axes[k,0 if arm=='c0' else 1]
            # Remove the same affine trend from every plotted held prediction.
            trend=affine@np.linalg.lstsq(affine,y,rcond=None)[0]
            ax.plot(times,y-trend,'k.',label='All measured points, fixed receiver correction')
            for q in own[:2]:
                g=q['grouped'];pred=np.asarray(g['score']['held_mean_hz'])
                # Native CFO plus integer alias minus receiver correction equals y.
                # The mean is in native lifted observation space, so compare
                # residuals directly using the saved held residual.
                residual=np.asarray(g['score']['held_residual_hz'])
                predicted=y[fh]-residual
                ax.plot(times[fh],predicted-trend[fh],'o',label=f"{q['norad']} held prediction, RMS {g['score']['rms_hz']:.1f} Hz")
            ax.axhline(0,color='gray',linewidth=.5);ax.set_title(f"Seed {fold['seed']} / {arm}: held blocks {fold['family_held_groups']}")
            ax.set_ylabel('CFO after shared affine removal (Hz)');ax.legend(fontsize=8)
    for ax in axes[-1]:ax.set_xlabel('Scan time (s)')
    fig.suptitle('52311 never enters receiver calibration: grouped prediction of its 20-point RX2 CH8 curve\nSame saved random scan groups; standard causal phase prior ±15 s; graph/candidate nomination remain conditional',fontsize=12)
    fig.tight_layout();fig.savefig(OUT/'family-grouped-predictions.png',dpi=160);fig.savefig(OUT/'family-grouped-predictions.pdf');plt.close(fig)
    for key in ('target66102_margin','family_margin','target66102_held_rms_hz','family_held_rms_hz','training_phase_change_s','nominal52311_phase_s','nominal52311_rms_hz','family_all_data_posterior_boundary_mass','affine_rms_hz','quadratic_curvature_hz_s2','endpoint_change_from_original_fold_km'):
        vals=[r[key] for r in summary['folds']];summary[key+'_range']=[min(vals),max(vals)]
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    with (OUT/'fold-summary.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(summary['folds'][0]));writer.writeheader();writer.writerows(summary['folds'])
    with (OUT/'point-accounting.csv').open('w') as f:
        fields=['observation_id','time_s','receiver','channel']+[f"seed_{fold['seed']}_role" for fold in a['folds']]
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for oid,t in zip(a['family']['observation_ids'],a['family']['times_s'],strict=True):
            row=dict(observation_id=oid,time_s=t,receiver=2,channel=8)
            for fold in a['folds']:
                train,held=replay_split(np.array([t]),fold['split'])
                row[f"seed_{fold['seed']}_role"]='removed_training' if train[0] else 'held' if held[0] else 'guard_purged'
            writer.writerow(row)
    (OUT/'manifest.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name not in ['manifest.json']},indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k.endswith('_range')},indent=2))


if __name__=='__main__':main()
