"""Scientific figures and complete tables for bounded outlier mechanisms."""
from pathlib import Path
import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from run_algo01_ds23_sample import ROOT,read,write
from probe_ds23_worst_association_bottleneck import setup,build,inventory
from report_algo02_ds23 import position_error

OUT=Path(__file__).resolve().parents[1]
COLORS={'c0':'#2c719f','fitted_c':'#b94b4f'}
NAMES={'noise_only':'Noise only','all_nuisance':'All nuisances','known_phase':'Phase known',
       'known_receiver':'Receiver known','all_known':'All known'}


def table(name,rows):
    with (OUT/'tables'/name).open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n')
        writer.writeheader();writer.writerows(rows)


def synthetic_plots():
    rows=[read(p) for p in sorted((OUT/'synthetic').glob('DS23-*.json'))]
    summary=read(OUT/'synthetic/evaluation.json')['summary'];table('synthetic_summary.csv',summary)
    detailed=[]
    for r in rows:
        for arm,s in r['arms'].items():
            detailed.append(dict(case=r['case'],site_index=r['site_index'],draw=r['draw'],variant=r['variant'],arm=arm,
                error_km=s['synthetic_position_error_km'],east_km=s['endpoint_east_north_km'][0],north_km=s['endpoint_east_north_km'][1],
                RMS_hz=s['RMS_hz'],loss=s['negative_twice_elbo'],all_gates_pass=s['original_gate_counts']['all_original_gates_pass'],
                phase_change_s=s['final_phase_change_s'],boundary=s['at_search_boundary']))
    table('synthetic_instances.csv',detailed)
    fig,axes=plt.subplots(1,2,figsize=(12,5.5),constrained_layout=True)
    for ax,case in zip(axes,('DS23-0081','DS23-0326'),strict=True):
        for k,v in enumerate(NAMES):
            for arm,offset in [('c0',-.13),('fitted_c',.13)]:
                selected=[r for r in detailed if r['case']==case and r['variant']==v and r['arm']==arm]
                y=np.array([r['error_km'] for r in selected]);xx=k+offset+np.linspace(-.045,.045,6)
                ax.scatter(xx,y,color=COLORS[arm],s=22,label=arm if k==0 else None)
                ax.plot([k+offset-.09,k+offset+.09],[np.median(y)]*2,c=COLORS[arm],lw=2)
        ax.set_yscale('log');ax.set_ylim(.001,30);ax.axhline(.5,color='gray',ls=':')
        ax.set_xticks(range(5),NAMES.values(),rotation=25,ha='right');ax.set(title=case,ylabel='Synthetic position error (km)')
        ax.grid(axis='y',alpha=.2);ax.legend()
    fig.suptitle('Exact outlier sampling: 6 common draws per variant, cold start at regional center\nKnown-parameter controls use synthetic truth; these are NOT real-data accuracy gains')
    fig.savefig(OUT/'figures/synthetic_controls.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,5.5),constrained_layout=True)
    for ax,case in zip(axes,('DS23-0081','DS23-0326'),strict=True):
        for site,marker in [(0,'o'),(1,'s')]:
            truth=np.array([(-5.,5.),(5.,-5.)][site]);ax.scatter(*truth,c='black',marker='*',s=170,zorder=5)
            for r in detailed:
                if r['case']!=case or r['variant']!='all_nuisance' or r['site_index']!=site:continue
                ax.plot([truth[0],r['east_km']],[truth[1],r['north_km']],c=COLORS[r['arm']],alpha=.5,lw=.8)
                ax.scatter(r['east_km'],r['north_km'],c=COLORS[r['arm']],marker=marker,s=35)
        ax.scatter(0,0,c='green',marker='+',s=110,label='Common optimizer start')
        ax.set(xlim=(-13,13),ylim=(-13,13),xlabel='East of region center (km)',ylabel='North of region center (km)',title=case)
        ax.set_aspect('equal');ax.grid(alpha=.25);ax.legend(loc='upper left',fontsize=8)
    fig.suptitle('All-nuisance simulation: black stars = synthetic truths; blue = c=0; red = fitted-c\nLines show truth-to-error displacement, NOT optimizer paths. All 24 arms pass residual gates.')
    fig.savefig(OUT/'figures/synthetic_endpoints.png',dpi=170);plt.close(fig)


def family_plots():
    data=read(OUT/'evidence/family_58590.json');records=data['records'];rows=[]
    limit=1.05*max(abs(v) for r in records if r['arm']=='fitted_c' for t in r['tracks'] for v in t['shared_phase_residual_hz'])
    for r in records:
        for t in r['tracks']:
            rows.append(dict(arm=r['arm'],location=r['location'],version=r['version'],component=t['member']['component'],
                receiver=t['member']['receiver'],channel=t['member']['channel'],points=t['member']['points'],
                shared_phase_s=r['shared']['phase_s'],independent_phase_s=t['independent_phase_fit']['phase_s'],
                shared_conditional_RMS_hz=t['shared_phase_rms_hz'],noise_screen=t['shared_phase_noise']['noise_screen_pass']))
    table('58590_profiles.csv',rows)
    fig,axes=plt.subplots(2,2,figsize=(12,8),constrained_layout=True)
    for row,location in enumerate(('endpoint','diagnostic_point')):
        for col,version in enumerate(('causal','following')):
            ax=axes[row,col];r=next(r for r in records if r['arm']=='fitted_c' and r['location']==location and r['version']==version)
            for k,t in enumerate(r['tracks']):
                m=t['member'];ax.plot(t['times'],t['shared_phase_residual_hz'],'.-',ms=3,lw=.7,
                    label=f"RX{m['receiver']} CH{m['channel']} ({m['points']} pts)",color=plt.get_cmap('tab10')(k))
            ax.axhline(0,c='gray',lw=.6);ax.grid(alpha=.2)
            ax.set(title=f"{location.replace('_',' ')} / {version}: RMS {r['shared']['conditional_rms_hz']:.1f} Hz",
                   xlabel='Time in scan (s)',ylabel='Conditional cavity residual (Hz)',ylim=(-limit,limit))
            if row==col==0:ax.legend(fontsize=8)
    fig.suptitle('58590: receiver prior calibrated without this family; one common phase fitted to all five tracks\nCorrelated radio/fragment uncertainty retained; future elements are diagnostic only')
    fig.savefig(OUT/'figures/58590_causal_following.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),constrained_layout=True)
    for ax,location in zip(axes,('endpoint','diagnostic_point'),strict=True):
        for version,offset,marker in [('causal',-.08,'o'),('following',.08,'s')]:
            r=next(r for r in records if r['arm']=='fitted_c' and r['location']==location and r['version']==version)
            ax.scatter(np.arange(5)+offset,[t['independent_phase_fit']['phase_s']-r['shared']['phase_s'] for t in r['tracks']],marker=marker,label=version)
        ax.axhline(0,c='gray',ls=':');ax.set_xticks(range(5),[f"RX{t['member']['receiver']} CH{t['member']['channel']}\n{min(t['times']):.0f}–{max(t['times']):.0f}s" for t in r['tracks']],fontsize=8)
        ax.set(title=location.replace('_',' '),ylabel='Per-track phase minus common phase (s)');ax.grid(alpha=.2);ax.legend()
    fig.suptitle('Following TLE changes the common phase by ≈1 s, but leaves the track disagreement\nPoint estimates only; no independent phase uncertainty claim')
    fig.savefig(OUT/'figures/58590_phase_consistency.png',dpi=170);plt.close(fig)
    selected=[r for r in data['decomposition'] if r['arm']=='fitted_c' and r['location']=='endpoint' and r['norad']==58590]
    fig,axes=plt.subplots(5,3,figsize=(15,15),constrained_layout=True)
    for k,r in enumerate(selected):
        t=np.array(r['times']);y=np.array(r['native_values_hz']);res=np.array(r['conditional_residual_hz'])
        axes[k,0].scatter(t,y/1000,s=9,c='black',label='GLRT');axes[k,0].plot(t,(y-res)/1000,c='tab:orange',label='Orbit + fitted radio/fragment')
        axes[k,1].plot(t,res,'.-',ms=3);axes[k,1].axhline(0,c='gray',lw=.6)
        for name in ('radio','smooth','phase','orbit'):
            v=np.array(r['contributions_hz'][name]);axes[k,2].plot(t,v-v[0],label=name)
        axes[k,0].set_title(f"RX{r['receiver']} CH{r['channel']}, {len(t)} points")
        axes[k,1].set_title(f"Residual RMS {np.sqrt(np.mean(res**2)):.1f} Hz")
        axes[k,2].set_title('Nuisance contribution relative to first point')
        for col in range(3):axes[k,col].grid(alpha=.2);axes[k,col].set_xlabel('Time in scan (s)')
        axes[k,0].set_ylabel('Native CFO (kHz)');axes[k,1].set_ylabel('Hz');axes[k,2].set_ylabel('Hz')
    axes[0,0].legend(fontsize=7);axes[0,2].legend(fontsize=8)
    fig.suptitle('0081 / 58590 at published endpoint: full fitted model can hide conflicting nuisance explanations\nNative alias gauges preserved; fragment constants have zero change in the right column')
    fig.savefig(OUT/'figures/58590_native_and_decomposition.png',dpi=140);plt.close(fig)


def additional_plots():
    cross=read(OUT/'evidence/cross_owner_58590.json')['rows']
    table('58590_cross_owner.csv',[{k:r[k] for k in ('arm','location','split','training_owner','training_points','held_points','phase_s','held_RMS_hz','held_quadratic')} for r in cross])
    fig,axes=plt.subplots(1,2,figsize=(11,4.5),constrained_layout=True)
    for ax,location in zip(axes,('endpoint','diagnostic_point'),strict=True):
        rows=[r for r in cross if r['arm']=='fitted_c' and r['location']==location]
        ax.bar(range(4),[r['held_RMS_hz'] for r in rows],color=['#447ba4','#447ba4','#bc7650','#bc7650'])
        ax.set_xticks(range(4),[f"Train {'RX' if r['split']=='receiver' else 'CH'}{r['training_owner']}\npredict other" for r in rows],fontsize=8)
        ax.set(title=location.replace('_',' '),ylabel='Held raw prediction innovation RMS (Hz)',ylim=(0,2000));ax.grid(axis='y',alpha=.2)
    fig.suptitle('58590: independently fitting one owner does not resolve the other receiver\nHeld points never fit phase/radio; correlated uncertainty retained; phase estimation uncertainty omitted')
    fig.savefig(OUT/'figures/58590_cross_owner.png',dpi=160);plt.close(fig)
    power=read(OUT/'evidence/DS23-0326_unit_power.json')
    native=read(OUT/'evidence/native_recovery_v2/DS23-0326.json')['methods']['persistent5s']
    audit=read(ROOT/'reports/2026_10_22_ds23_dbg01_iteration_001/evidence/DS23-0326/DBG01_audit.json')
    truth=np.array(audit['arms']['fitted_c']['diagnostic_point']['endpoint_east_north_km'])
    rows=[]
    for name,arms,count in [('Reference',power['original_arms'],71),('Unit track power',power['arms'],71),('Native predictive recovery',native['arms'],79)]:
        for arm,r in arms.items():
            rows.append(dict(method=name,arm=arm,error_km=position_error(r['endpoint_latlon']),
                RMS_hz=r['RMS_hz'],associated=count,total=539,percent=100*count/539))
    table('0326_real_controls.csv',rows)
    fig,axes=plt.subplots(1,3,figsize=(13,4.6),constrained_layout=True)
    names=['Reference','Unit track power','Native predictive recovery']
    for ax,key,label in zip(axes,('error_km','RMS_hz','percent'),('Position error (km)','Curved residual RMS (Hz)','Associated GLRT (%)'),strict=True):
        for arm,offset in [('c0',-.18),('fitted_c',.18)]:
            values=[next(r[key] for r in rows if r['method']==n and r['arm']==arm) for n in names]
            ax.bar(np.arange(3)+offset,values,width=.34,color=COLORS[arm],label=arm)
        ax.set_xticks(range(3),['Reference','Unit power','+8 predictive'],rotation=20,ha='right');ax.set_ylabel(label);ax.grid(axis='y',alpha=.2)
    axes[0].legend(fontsize=8);fig.suptitle('0326: better frequency fit or more associated points did not improve position\nSame original observations retained; recovered points belong to an already present family')
    fig.savefig(OUT/'figures/0326_real_controls.png',dpi=170);plt.close(fig)

    d=setup('DS23-0326');selection=read(OUT/'evidence/native_recovery_v2/DS23-0326_persistent5s_selection.json')['selected']
    chosen={oid for s in selection for oid in s['observation_ids']}
    obs=[o for o in d['observations'] if o['receiver']==1 and o['channel']==3 and o['time_s']>220]
    fig,ax=plt.subplots(figsize=(9,4.5),constrained_layout=True)
    for accepted,color,label in [(False,'gray','Other original GLRT'),(True,'#b44290','New predictive association to 58367')]:
        o=[r for r in obs if (r['observation_id'] in chosen)==accepted]
        ax.scatter([r['time_s'] for r in o],[r['measured_cfo_hz']/1000 for r in o],s=35,c=color,label=label)
    ax.set(xlabel='Time in scan (s)',ylabel='Native GLRT CFO (kHz)',title='0326 RX1 CH3: 8 supported new points, no new satellite family')
    ax.grid(alpha=.2);ax.legend(fontsize=9);fig.savefig(OUT/'figures/0326_recovered_points.png',dpi=160);plt.close(fig)


def coverage_plot():
    d=setup('DS23-0326');inv=inventory(d,'fitted_c');owned=set(inv['accepted_observation_ids'])
    native={o['observation_id']:o['measured_cfo_hz'] for o in d['observations']}
    graph={oid for t in d['scan'].tracks for oid in t['observation_ids']};counts=[]
    fig,axes=plt.subplots(2,4,figsize=(15,7),constrained_layout=True)
    for rx in (1,2):
        for ch in range(1,5):
            ax=axes[rx-1,ch-1];obs=[o for o in d['observations'] if o['receiver']==rx and o['channel']==ch]
            for tag,color in [('associated','#3075a7'),('unassociated graph','#dc4b55'),('outside graph','#999999')]:
                subset=[o for o in obs if ('associated' if o['observation_id'] in owned else 'unassociated graph' if o['observation_id'] in graph else 'outside graph')==tag]
                ax.scatter([o['time_s'] for o in subset],[o['measured_cfo_hz']/1000 for o in subset],s=10,c=color,label=tag)
            for t in d['scan'].tracks:
                if t['receiver']==rx and t['channel']==ch:
                    ax.plot(t['times'],np.array([native[oid] for oid in t['observation_ids']])/1000,c='black',lw=.6,alpha=.5)
            ax.axvspan(220,300,color='gold',alpha=.1);ax.set(title=f'RX{rx} CH{ch}',xlabel='Time (s)',ylabel='CFO (kHz)',xlim=(0,300));ax.grid(alpha=.2)
            for window,start,end in [('whole',0,300),('late',220,300)]:
                sub=[o for o in obs if start<=o['time_s']<=end]
                counts.append(dict(receiver=rx,channel=ch,window=window,total=len(sub),associated=sum(o['observation_id'] in owned for o in sub),
                    unassociated_graph=sum(o['observation_id'] in graph-owned for o in sub),outside_graph=sum(o['observation_id'] not in graph for o in sub)))
    axes[0,0].legend(fontsize=7);fig.suptitle('0326: where independent evidence could be recovered\nBlue = associated; red = unassociated graph points; gray = outside graph; black = existing graph curves')
    fig.savefig(OUT/'figures/0326_evidence_inventory.png',dpi=160);plt.close(fig);table('0326_window_counts.csv',counts)
    write(OUT/'evidence/0326_inventory.json',inv)


def main():
    synthetic_plots();family_plots();coverage_plot();additional_plots()


if __name__=='__main__':main()
