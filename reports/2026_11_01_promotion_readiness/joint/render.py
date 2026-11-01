"""Render saved paired diagnostic results; truth appears only as an endpoint."""
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import joint as j

FIG=j.OUT/'figures';FIG.mkdir(exist_ok=True)
CASES=['DS26-0203','DS26-0070']


def context(case):
    j.rec.CATALOGUES=j.ev.ROOTS['DS26']/'catalogues';d,z,_=j.ev.load_case(case)
    observations=j.read(Path(z['native_path'])/'observations.json');owners=z['baseline_owners']['fitted_c']
    tracked={o for t in d['scan'].tracks for o in t['observation_ids']}
    targets=j.read(j.OUT/'protocol.json')['cases'][case]['targets']
    colors=['tab:red','tab:blue'];fig,axes=plt.subplots(2,8,figsize=(22,7),sharex=True,sharey=True)
    score,saxes=plt.subplots(2,8,figsize=(22,7),sharex=True,sharey=True)
    for rx in [1,2]:
        for ch in range(1,9):
            ax=axes[rx-1,ch-1];sx=saxes[rx-1,ch-1];oo=[o for o in observations if o['receiver']==rx and o['channel']==ch]
            for kind,color,marker,label in [('other','0.65','.','other published owner'),('tracked','tab:orange','.','graph tracked, unassociated'),('untracked','black','x','untracked')]+[(n,c,'o',str(n)) for n,c in zip(targets,colors)]:
                rr=[o for o in oo if (owners.get(o['observation_id'])==kind if isinstance(kind,int) else
                    o['observation_id'] in owners and owners[o['observation_id']] not in targets if kind=='other' else
                    o['observation_id'] not in owners and o['observation_id'] in tracked if kind=='tracked' else o['observation_id'] not in tracked and o['observation_id'] not in owners)]
                if rr:ax.scatter([o['time_s'] for o in rr],[o['measured_cfo_hz']/1e3 for o in rr],s=8 if isinstance(kind,int) else 4,c=color,marker=marker,label=label)
            if oo:sc=sx.scatter([o['time_s'] for o in oo],[o['measured_cfo_hz']/1e3 for o in oo],c=[o['fractional_margin'] for o in oo],s=5,cmap='viridis',vmin=0,vmax=1)
            for row,i,s in zip(d['problems']['fitted_c'][0].rows,d['problems']['fitted_c'][0].members,d['problems']['fitted_c'][0].slices):
                t=d['scan'].tracks[i]
                if row['candidate_norad'] in targets and t['receiver']==rx and t['channel']==ch:
                    ax.axvspan(t['start_s'],t['end_s'],color=colors[targets.index(row['candidate_norad'])],alpha=.08)
            ax.set_title(f'RX{rx} CH{ch}');sx.set_title(f'RX{rx} CH{ch}')
            ax.grid(alpha=.2);sx.grid(alpha=.2)
    for aa in [axes,saxes]:
        for ax in aa[-1]:ax.set_xlabel('scan time (s)')
        for ax in aa[:,0]:ax.set_ylabel('native CFO (kHz)')
    handles={label:handle for ax in axes.flat for handle,label in zip(*ax.get_legend_handles_labels())}
    fig.legend(handles.values(),handles.keys(),loc='upper center',ncol=5);fig.suptitle(case+' published native evidence; shading = target graph-track span',y=.98)
    fig.tight_layout(rect=(0,0,1,.92));fig.savefig(FIG/(case+'-context.png'),dpi=150);plt.close(fig)
    score.colorbar(sc,ax=list(saxes.flat),label='native GLRT fractional margin (not a calibrated probability)',shrink=.7)
    score.suptitle(case+' native detector scores');score.subplots_adjust(wspace=.15,hspace=.3,right=.88);score.savefig(FIG/(case+'-scores.png'),dpi=150);plt.close(score)


def rows_table():
    rows=[]
    for case in CASES:
        for path in sorted((j.OUT/case).rglob('*fits.json')):
            for r in j.read(path):
                rows.append(dict(case=case,scope='supplement' if 'supplement' in path.parts else 'frozen',hypothesis=path.parent.name,
                    arm=r['arm'],start=r['start'],status=r['status'],qualified=r['qualified'],objective=r.get('objective'),
                    error_m=r.get('error_m'),rms_hz=r.get('rms_hz'),phase_change_s=r.get('history',[{}])[-1].get('phase_change_s'),
                    optimizer_success=r.get('optimizer_success'),all_gates_pass=r.get('all_gates_pass'),lost=len(r.get('lost_ids',[])),
                    reassigned=len(r.get('reassigned_ids',[])),unexpected=len(r.get('unexpected_reassigned_ids',[])),
                    failed_gate_count=len(r.get('failed_gates',{})),exact_failures=sum(not q['all_pass'] for q in r.get('exact',[])),
                    native_hash=r.get('native_ids_sha256'),reason=r.get('reason'),path=str(path)))
    with (j.OUT/'fits.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
    return rows


def comparison(rows):
    fig,axes=plt.subplots(1,3,figsize=(15,4))
    records=j.read(j.OUT/'DS26-0070/predictive_summary.json')
    for name,arms in records.items():
        for a,color in [('c0','tab:blue'),('fitted_c','tab:orange')]:
            axes[0].plot(np.arange(1,6),arms[a]['gains'],'o-',label=a,color=color)
    axes[0].axhline(0,color='black',lw=1);axes[0].set(xlabel='random held-group fold',ylabel='incumbent − pair predictive score',title='0070 joint conditional prediction')
    axes[0].legend()
    for case,marker in [('DS26-0203','o'),('DS26-0070','s')]:
        baseline=j.read(j.OUT/case/'baseline.json')
        for a,color in [('c0','tab:blue'),('fitted_c','tab:orange')]:
            rr=[r for r in rows if r['case']==case and r['arm']==a and r['objective'] is not None]
            for r in rr:
                axes[1].scatter(baseline[a]['objective']-r['objective'],r['error_m']/1e3,marker=marker,c=color,s=35,alpha=.65)
                axes[2].scatter(r['phase_change_s'],r['failed_gate_count']+r['exact_failures'],marker=marker,c=color,s=35,alpha=.65)
    axes[1].axvline(0,color='black',lw=1);axes[1].set(xlabel='published − trial RF objective (unpenalized)',ylabel='evaluation position error (km)',title='All completed fits; none adopted')
    axes[1].legend(handles=[Line2D([],[],marker='o',ls='',color='0.3',label='0203'),Line2D([],[],marker='s',ls='',color='0.3',label='0070')],loc='upper right')
    axes[2].axvline(.01,color='black',ls='--',label='0.01 s closure gate');axes[2].set(xscale='log',xlabel='final phase-reference change (s)',ylabel='failed gates + failing exact family replays',title='Original qualification failures')
    axes[2].legend()
    for ax in axes:ax.grid(alpha=.2)
    fig.tight_layout();fig.savefig(FIG/'comparison.png',dpi=170);plt.close(fig)


def merge_residuals():
    curves=j.read(j.OUT/'DS26-0203/merge_audit/curves.json');fig,axes=plt.subplots(2,2,figsize=(13,7),sharex=True)
    for row,ns in enumerate([(67935,59360),(63377,68256)]):
        for n,color in zip(ns,['tab:red','tab:blue']):
            for q in curves:
                if q['arm']!='fitted_c' or q['norad']!=n:continue
                axes[row,0].plot(q['times_s'],np.array(q['values_hz'])/1e3,'.',ms=3,c=color,label=str(n))
                axes[row,1].plot(q['times_s'],q['residual_hz'],'.',ms=3,c=color,label=str(n))
        axes[row,0].set_ylabel('native graph CFO (kHz)');axes[row,1].set_ylabel('published conditional residual (Hz)')
        axes[row,0].set_title(f'{ns[0]} source and existing {ns[1]} (different RF channels)');axes[row,1].axhline(0,color='black',lw=1)
        for ax in axes[row]:
            handles={label:h for h,label in zip(*ax.get_legend_handles_labels())};ax.legend(handles.values(),handles.keys());ax.grid(alpha=.2)
    for ax in axes[-1]:ax.set_xlabel('scan time (s)')
    fig.tight_layout();fig.savefig(FIG/'0203-merge-native-residuals.png',dpi=170);plt.close(fig)


def orbit_overlays():
    case='DS26-0070';out=j.OUT/case;pairs=j.read(out/'pairs.json')['pairs'];h=pairs[0]
    fig,axes=plt.subplots(4,3,figsize=(17,13));parameters=[]
    from leo.analysis.research.retained_track_likelihood import PERIOD
    def wrapped(y):return (y+PERIOD/2)%PERIOD-PERIOD/2
    def break_wrap(x,y):
        xx=np.array(x);yy=wrapped(y);bad=np.flatnonzero(abs(np.diff(yy))>PERIOD/2)+1
        xx=np.insert(xx,bad,np.nan);yy=np.insert(yy,bad,np.nan);return xx,yy
    for ai,arm in enumerate(j.ARMS):
        saved=np.load(out/(arm+'-predictive-raw.npz'));times=saved['times_s'];owners=saved['owners'];groups=saved['groups'];phase=saved['phase_s'];q=saved['q'];values=saved['values_hz']
        for ni,(source,destination) in enumerate(zip(h['targets'],h['destinations'])):
            row=2*ai+ni;mask=owners==source;t=times[mask];g=groups[mask];qq=q[mask];y=values[mask];raw=saved[f'residual_{destination}'][:,mask]
            fit=j.rec.fit_predict(raw,t,qq,g,np.ones(len(t),bool),np.ones(len(t),bool),phase);k=int(np.argmin(abs(phase-fit['phase_map_s'])))
            lift=y.copy();rr=raw[k].copy();unique=np.unique(g)
            for group,alias in fit['alias_by_group'].items():lift[g==group]+=alias*PERIOD;rr[g==group]+=alias*PERIOD
            design=np.column_stack([(g==group)*300. for group in unique]+[qq*(t-150)*.5])/150.
            cov=np.linalg.inv(np.eye(design.shape[1])+design.T@design);beta=(rr/150)@design@cov
            orbital=y-raw[k];adjusted=orbital+150*design@beta;residual=lift-adjusted
            parameters.append(dict(arm=arm,source=source,destination=destination,phase_s=fit['phase_map_s'],aliases=fit['alias_by_group'],offsets_hz=beta[:-1]*300,rate_hz_s=beta[-1]*.5,
                residual=j.ev.diagnose.residual_stats(t,residual)))
            for group in unique:
                use=g==group;order=np.argsort(t[use]);tt=t[use][order];native=lift[use][order];phys=orbital[use][order];pred=adjusted[use][order];res=residual[use][order]
                axes[row,0].plot(tt,wrapped(native)/1e3,'.',ms=3,color='black')
                xx,yy=break_wrap(tt,phys);axes[row,0].plot(xx,yy/1e3,'--',lw=1,color='tab:blue')
                xx,yy=break_wrap(tt,pred);axes[row,0].plot(xx,yy/1e3,'-',lw=1,color='tab:red')
                axes[row,1].plot(tt,native/1e3,'.',ms=3,color='black');axes[row,1].plot(tt,phys/1e3,'--',lw=1,color='tab:blue');axes[row,1].plot(tt,pred/1e3,'-',lw=1,color='tab:red')
                axes[row,2].plot(tt,res,'.',ms=3)
            axes[row,0].set_ylabel(f'{arm}: {source}→{destination}\nCFO (kHz)');axes[row,2].axhspan(-150,150,color='0.8',alpha=.4);axes[row,2].axhline(0,color='black',lw=1)
            for ax in axes[row]:ax.grid(alpha=.2)
            np.savez_compressed(out/(arm+f'-{source}-conditional-full.npz'),times_s=t,groups=g,native_cavity_lifted_hz=lift,physical_orbit_hz=orbital,radio_adjusted_hz=adjusted,residual_hz=residual)
    for ax,title in zip(axes[0],['Wrapped cavity radio-subtracted native CFO','Same points and aliases lifted','Conditional residual; band = 150 Hz noise']):ax.set_title(title)
    for ax in axes[-1]:ax.set_xlabel('scan time (s)')
    fig.legend(handles=[Line2D([],[],marker='.',ls='',color='black',label='native, cavity radio subtracted'),Line2D([],[],ls='--',color='tab:blue',label='physical orbit at fitted shared phase'),Line2D([],[],color='tab:red',label='orbit + per-source offset + shared rate')],loc='upper center',ncol=3)
    fig.tight_layout(rect=(0,0,1,.96));fig.savefig(FIG/'0070-conditional-orbits-residuals.png',dpi=150);plt.close(fig)
    j.write(out/'conditional_full_parameters.json',parameters)


def predictive_decomposition():
    records=j.read(j.OUT/'DS26-0070/predictive_folds.json');fig,axes=plt.subplots(1,3,figsize=(15,4),sharex=True)
    table=[]
    for arm,color in [('c0','tab:blue'),('fitted_c','tab:orange')]:
        rows=[r for r in records if r['arm']==arm];folds=[r['fold']+1 for r in rows]
        axes[0].plot(folds,[r['gain'] for r in rows],'o-',c=color,label=arm)
        for k,target in enumerate([62320,63321]):
            gains=[r['baseline'][k]['predictive_score']-r['candidate'][k]['predictive_score'] for r in rows]
            axes[k+1].plot(folds,gains,'o-',c=color,label=arm)
            table.append(dict(arm=arm,target=target,gains=gains,mean=float(np.mean(gains)),wins=sum(v>0 for v in gains)))
    for ax,title in zip(axes,['Aggregate pair: 5/5 gains','62320 → 63571: 5/5 gains','63321 → 62422: 0/5 gains']):
        ax.axhline(0,c='black',lw=1);ax.set(title=title,xlabel='same random held-group fold',ylabel='incumbent − candidate predictive score');ax.grid(alpha=.2);ax.legend()
    fig.suptitle('Same joint-two-family cavity: aggregate gains compensate for one failing family')
    fig.tight_layout();fig.savefig(FIG/'0070-predictive-decomposition.png',dpi=170);plt.close(fig)
    j.write(j.OUT/'DS26-0070/predictive_per_family.json',table)


if __name__=='__main__':
    rows=rows_table();comparison(rows);merge_residuals();orbit_overlays();predictive_decomposition()
    for c in CASES:context(c)
