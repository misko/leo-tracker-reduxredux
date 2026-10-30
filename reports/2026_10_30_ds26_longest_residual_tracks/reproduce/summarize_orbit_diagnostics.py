"""Render compact top-five views from saved diagnostics, without inference."""
import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from debug_fast_graph_unassociated import read
from leo.analysis.research.graph_position_membership import native_polynomial
from inventory_ds26 import published_ids


def run(base):
    results=[read(p) for p in sorted(base.glob('*/result.json'))]
    fig,axes=plt.subplots(len(results),2,figsize=(17,3.6*len(results)),layout='constrained')
    summary=[]
    for result,axs in zip(results,axes,strict=True):
        row=result['row'];out=base/f"{row['rank']:02d}-{row['case']}"
        obs=read(row['observations_path']);byid={o['observation_id']:o for o in obs}
        terminal=read(row['terminal_path']);associated=published_ids(terminal,terminal['selected_arm'])
        track=read(row['tracks_path'])[row['track_index']]
        target=set(row['residual_observation_ids'])
        ids=[o for o in track['observation_ids'] if o in target]
        time=np.array([byid[o]['time_s'] for o in ids]);raw=np.array([byid[o]['measured_cfo_hz'] for o in ids])
        lane=[o for o in obs if (o['receiver'],o['channel'])==(row['receiver'],row['channel'])
              and row['start_s']-7<=o['time_s']<=row['end_s']+7]
        lane_rows=[dict(o,published_role='target_residual' if o['observation_id'] in target else
                        'associated' if o['observation_id'] in associated else 'other_unassociated') for o in lane]
        with (out/'raw_lane_points.csv').open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(lane_rows[0]));writer.writeheader();writer.writerows(lane_rows)
        ax,res=axs
        for role,color,size,label in [('associated','.7',12,'Published associated'),
            ('other_unassociated','darkorange',18,'Other unassociated'),('target_residual','crimson',22,'Target residual')]:
            selected=[o for o in lane_rows if o['published_role']==role]
            ax.scatter([o['time_s'] for o in selected],[o['measured_cfo_hz']/1000 for o in selected],s=size,c=color,label=label)
        for k,y in enumerate(native_polynomial(track,byid)):
            ax.plot(track['times'],y/1000,color='black',lw=1.3,label='Original graph polynomial' if k==0 else None)
        for arm,color,style in [('c0','#0072b2','--'),('fitted_c','#009e73','-')]:
            fit=result['trials'][arm]['constant'][0]
            pred=raw-np.asarray(fit['residual_hz'])
            pred[np.r_[False,abs(np.diff(pred))>100000]]=np.nan
            ax.plot(time,pred/1000,color=color,ls=style,lw=1.2,label=f"Causal diagnostic {arm}: {fit['norad']}")
            res.plot(time,fit['residual_hz'],'.-',ms=2.7,color=color,ls=style,
                     label=f"Frozen {arm}: {fit['rms_hz']:.1f} Hz RMS")
            if result.get('actual_pipeline_trial'):
                actual=result['actual_pipeline_trial']['arms'][arm]
                res.plot(actual['times_s'],actual['residual_hz'],color='#cc79a7',ls=style,lw=1,
                         label=f"Actual inclusion trial {arm}: {actual['RMS_hz']:.1f} Hz")
            for model in ('constant','small_rate'):
                nominees=result['top_competitors'][arm][model]
                winner=nominees[0];second=nominees[1]
                summary.append(dict(rank=row['rank'],case=row['case'],track_id=row['track_id'],receiver=row['receiver'],
                    channel=row['channel'],span_s=row['span_s'],residual_points=row['residual_points'],arm=arm,model=model,
                    norad=winner['norad'],name=winner['satellite_name'],rms_hz=winner['rms_hz'],cost=winner['cost'],
                    runnerup_norad=second['norad'],runnerup_rms_hz=second['rms_hz'],runnerup_cost=second['cost'],
                    cost_margin=second['cost']-winner['cost'],phase_s=winner['phase_s'],bias_hz=winner['offset_hz'],rate_hz_s=winner['rate_hz_s'],
                    minimum_elevation_deg=winner['minimum_elevation_deg'],TLE_age_hours=winner['element_age_at_origin_s']/3600,
                    position_name=winner['position_name'],failed_diagnostic_gates=';'.join(winner['failed_gates']),
                    diagnostic_only=True,receiver_calibration_frozen=True))
        best=result['top_competitors']['fitted_c']['constant'][0]
        second=result['top_competitors']['fitted_c']['constant'][1]
        pad=max(15.,np.ptp(raw)/1000*.12)
        ax.set_ylim(raw.min()/1000-pad,raw.max()/1000+pad)
        ax.set_title(f"#{row['rank']} {row['case']} RX{row['receiver']} CH{row['channel']} — {row['span_s']:.2f} s, {row['residual_points']} points",fontsize=11)
        ax.set_ylabel('Native GLRT CFO (kHz; target range zoom)')
        ax.legend(fontsize=7,ncol=2,loc='best')
        res.axhline(0,c='.5',lw=.6)
        res.set_ylabel('Residual after alias + constant (Hz)')
        res.set_title(f"Candidate {best['norad']} ({best['satellite_name']}); runner-up {second['norad']}: {second['rms_hz']:.0f} Hz RMS",fontsize=10)
        res.legend(fontsize=7,ncol=2)
        for axis in axs:axis.grid(alpha=.2);axis.set_xlabel('Device time (s)')
    fig.suptitle('Five longest DS26 graph tracks remaining after published ALGO03\nCausal orbit diagnostics at frozen baseline receiver calibration; matched c arms, no new associations',fontsize=15)
    fig.savefig(base/'top5-overview.png',dpi=150);fig.savefig(base/'top5-overview.pdf');plt.close(fig)
    with (base/'summary.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(summary[0]));writer.writeheader();writer.writerows(summary)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('base',type=Path)
    run(parser.parse_args().base)
