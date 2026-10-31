"""Render matched conditional correction diagnostics and explicit gate receipts."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def failures(noise,n):
    return [name for name,bad in (
        ('mean',noise['mean_z']>3),('slope',noise['slope_z']>3),
        ('quadratic',noise['quadratic_bic_gain']>10),('step',noise['maximum_step_z']>4),
        ('ACF',abs(noise['lag1_acf'])>4/np.sqrt(n))) if bad]


def pooled(evaluations,key):
    if not evaluations:return None
    return float(np.sqrt(sum(z['points']*z[key]['RMS_hz']**2 for z in evaluations)/sum(z['points'] for z in evaluations)))


def run(base):
    result=json.loads((base/'result.json').read_text());summary=[];held_rows=[]
    for case in result['cases']:
        fig,axes=plt.subplots(3,4,figsize=(20,10),sharex=True,sharey=True,layout='constrained')
        for row in case['rows']:
            ri=['receiver','satellite','joint'].index(row['model'])
            ci=2*['control','addition'].index(row['role'])+['c0','fitted_c'].index(row['arm'])
            ax=axes[ri,ci];z=row['evaluations'][0];t=np.asarray(z['times_s'])
            before=np.asarray(z['baseline']['residual_hz']);after=np.asarray(z['corrected']['residual_hz'])
            # Effective centered correction accounts for the same reprofiled
            # nuisance constant in both variants. Raw model predictions remain
            # separately retained in the JSON correction_hz field.
            effect=before-after
            ax.plot(t,before,'k.-',lw=.65,ms=2,label='Target before')
            ax.plot(t,effect,color='#df8700',lw=1.7,label='Witness correction, centered')
            ax.plot(t,after,'.-',color='#2878b5',lw=.65,ms=2,label='Target after')
            ax.axhline(0,color='.5',lw=.5);ax.grid(alpha=.2)
            failed=failures(z['corrected']['noise'],z['points'])
            ax.set_title(f"{row['role']} / {row['arm']} / {row['model']}\nRMS {z['baseline']['RMS_hz']:.1f} → {z['corrected']['RMS_hz']:.1f} Hz; fails: {', '.join(failed)}",fontsize=9)
            if ri==2:ax.set_xlabel('Device time (s)')
            if ci==0:ax.set_ylabel('Residual / correction (Hz)')
            h=row['evaluations'][1:]
            summary.append(dict(case=case['case'],role=row['role'],arm=row['arm'],model=row['model'],
              target_points=z['points'],target_baseline_RMS_hz=z['baseline']['RMS_hz'],target_corrected_RMS_hz=z['corrected']['RMS_hz'],
              target_corrected_lag1_acf=z['corrected']['lag1_acf'],target_failed_screens=','.join(failed),
              target_slope_z=z['corrected']['noise']['slope_z'],target_step_z=z['corrected']['noise']['maximum_step_z'],
              held_tracks=len(h),held_baseline_RMS_hz=pooled(h,'baseline'),held_corrected_RMS_hz=pooled(h,'corrected'),
              held_worsened_tracks=sum(a['corrected']['RMS_hz']>a['baseline']['RMS_hz'] for a in h),
              original_full_calibration_RMS_hz=row['full_calibration_target_metrics']['RMS_hz'],
              curved_objective_replay_delta=row['curved_objective_replay_delta']))
            for a in h:
                held_rows.append(dict(case=case['case'],role=row['role'],arm=row['arm'],model=row['model'],component=a['component'],
                  points=a['points'],baseline_RMS_hz=a['baseline']['RMS_hz'],corrected_RMS_hz=a['corrected']['RMS_hz'],
                  worsened=a['corrected']['RMS_hz']>a['baseline']['RMS_hz'],
                  failed_screens=','.join(failures(a['corrected']['noise'],a['points']))))
        axes[0,0].legend(fontsize=8,loc='lower left')
        fig.suptitle(case['case']+' — target-excluded residual correction; fixed 6 s / 150 Hz priors, seed 20261031\nWhole witness tracks held out; inherited frozen geometry; addition endpoint target-informed; no localization/acceptance change',fontsize=13)
        fig.savefig(base/(case['case']+'.png'),dpi=150)
        fig.savefig(base/(case['case']+'.pdf'));plt.close(fig)
    for name,rows in (('summary.csv',summary),('held_witnesses.csv',held_rows)):
        with (base/name).open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps([r for r in summary if r['case']=='DS26-0223' and r['model']=='joint'],indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('base',type=Path);run(p.parse_args().base)
