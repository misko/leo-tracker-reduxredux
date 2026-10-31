"""Describe existing causal nominations and exact rejected fits of residual sources."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def read(p):return json.loads(Path(p).read_text())
def main(root):
    result=[];sources={};out=root/'diagnostics';out.mkdir(exist_ok=True)
    for ds in ('DS26','DS27'):
        for rank,row in enumerate(read(root/(ds+'-top10.json')),1):
            recovery=Path(row['recovery_path']);parent=recovery/row['track_id']
            annotation=parent/'annotation/result.json'
            identity=read(annotation)['annotation'] if annotation.exists() else None
            options=([Path('/srv/bulk/leo/research/ds26-confident-recovery-20261031/targets')/row['case']/row['track_id']/'conditional']
                if ds=='DS26' else [Path('/srv/bulk/leo/research/ds27-confident-recovery-20261031')/row['case']/'conditional'])
            options+=[parent/'trial']
            fit_path=next((p/name for p in options for name in ('target_0.json','new_family.json') if (p/name).exists() and any(t['component']==row['key'] for t in read(p/name)['target_entries'])),None)
            folder=fit_path.parent if fit_path else None
            record={k:row[k] for k in ('case','key','points','duration_s','start_s','end_s','parent_points','parent_graph_pieces','max_gap_s','track_id')}
            record.update(rank=rank,identity=identity,fit_path=str(folder) if folder else None,arms={})
            fig,axs=plt.subplots(2,2,figsize=(13,8),constrained_layout=True)
            inv=read(row['inventory_path']);native=Path(inv['job']['root'])/inv['job']['case'];tracks=read(native/'tracks.json');track=tracks[row['track_index']]
            obs=read(native/'observations.json');lane=[o for o in obs if o['receiver']==row['receiver'] and o['channel']==row['channel'] and row['start_s']-10<=o['time_s']<=row['end_s']+10]
            ids=set(row['observation_ids']);target=[o for o in lane if o['observation_id'] in ids];context=[o for o in lane if o['observation_id'] not in ids]
            axs[0,0].scatter([o['time_s'] for o in context],[o['measured_cfo_hz']/1000 for o in context],s=8,color='#bbb',label='Other native GLRT (ownership mixed)')
            axs[0,0].scatter([o['time_s'] for o in target],[o['measured_cfo_hz']/1000 for o in target],s=12,color='#d42d65',label='Ranked unassociated fragment')
            axs[0,0].set(ylabel='Native CFO (kHz)',xlabel='Scan time (s)',title='Original GLRT; no alias duplication');axs[0,0].legend(fontsize=7)
            use=row['source_local_indices'];axs[0,1].scatter(np.array(track['times'])[use],np.array(track['values'])[use]/1000,s=10,color='#d42d65',label='Unassociated fragment, alias lifted')
            if folder:
                fit=read(fit_path);audit=read(folder/'exact_owner_replay.json') if (folder/'exact_owner_replay.json').exists() else None
                for arm,color in [('c0','#176bbb'),('fitted_c','#ee8d16')]:
                    r=fit['arms'][arm];diag=next((d for d in r.get('target_diagnostics',r.get('family',{}).get('diagnostics',[])) if d['component']==row['key']),None)
                    family_noise=None
                    if diag and 'raw_residual_hz' in diag:
                        family_noise=diag['noise'];bias=diag['profile_bias_hz']
                        diag=dict(diag,RMS_hz=diag['profile_RMS_hz'],bias_hz=bias,
                            residual_hz=(np.array(diag['raw_residual_hz'])-bias).tolist(),
                            predicted_CFO_hz=(np.array(diag['prediction_CFO_hz'])+bias).tolist())
                    if diag:
                        times=np.array(diag['times_s']);res=np.array(diag['residual_hz']);record['arms'][arm]=dict(RMS_hz=diag['RMS_hz'],bias_hz=diag['bias_hz'],phase_change_s=r['final_phase_change_s'])
                        axs[0,1].plot(times,np.array(diag['predicted_CFO_hz'])/1000,color=color,label=f'{arm} rejected candidate')
                        axs[1,0].plot(times,res,'.-',lw=.5,ms=3,color=color,label=arm)
                    failed={}
                    if audit:
                        for a in audit['rows']:
                            if a['role']=='target_0' and a['arm']==arm:
                                for family in a['exact_family_replays']:
                                    for k,v in family['all_gate_slacks'].items():
                                        if v<0:failed[k]=min(failed.get(k,0),v)
                    record['arms'].setdefault(arm,{})['failed_exact_gates']=failed
                    record['arms'][arm]['lost_points']=r.get('lost_points');record['arms'][arm]['paired_valid']=fit['paired_valid']
                    record['arms'][arm]['new_family_noise']=family_noise
                for p in (fit_path,folder/'exact_owner_replay.json'):
                    if p.exists():sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
            else:
                axs[1,0].text(.5,.5,'No qualified joint nomination / retained fit\nNo orbit is assigned by this plot',ha='center',transform=axs[1,0].transAxes)
            axs[0,1].set(ylabel='Lifted CFO (kHz)',xlabel='Scan time (s)',title='Best retained causal hypothesis; not an accepted match');axs[0,1].legend(fontsize=7)
            axs[1,0].axhline(0,color='k',lw=.7);axs[1,0].set(ylabel='CFO residual (Hz)',xlabel='Scan time (s)',title='Residual against the retained candidate model')
            if folder:axs[1,0].legend(fontsize=7)
            if identity:
                votes=identity['votes'];axs[1,1].bar(range(len(votes)),[v['margin'] for v in votes],color=['#176bbb' if v['arm']=='c0' else '#ee8d16' for v in votes])
                axs[1,1].set_xticks(range(len(votes)),[str(v['norad'])+'\n'+v['arm'] for v in votes],fontsize=7)
                axs[1,1].set(ylabel='Held-out score margin (not probability)',title=identity['status'])
            else:axs[1,1].text(.5,.5,'No retained independent nomination\nRequires a fresh causal search',ha='center',transform=axs[1,1].transAxes)
            fig.suptitle(f"{row['case']} · {row['key'].split('-RF')[0]} · {row['points']} points / {row['duration_s']:.1f} s")
            name=f'{ds}-{rank:02d}-{row["case"]}.png';fig.savefig(out/name,dpi=150);plt.close(fig);record['figure']=name;result.append(record)
            if annotation.exists():sources[str(annotation)]=hashlib.sha256(annotation.read_bytes()).hexdigest()
    (out/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'source-sha256.json').write_text(json.dumps(sources,indent=2)+'\n')
    for r in result:
        print(r['case'],r['key'].split('-RF')[0],r['identity']['norad'] if r['identity'] else None,
            {a:dict(RMS_hz=v.get('RMS_hz'),failed={k:round(x,3) for k,x in v['failed_exact_gates'].items()}) for a,v in r['arms'].items()})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);main(p.parse_args().root)
