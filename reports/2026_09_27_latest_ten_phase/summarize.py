"""Real scan summaries, phase/CFO scatter galleries and randomized visit controls."""
from pathlib import Path
from datetime import datetime,timezone
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from phase import wrap

HERE=Path(__file__).resolve().parent
def circ(values):return float(np.angle(np.mean(np.exp(1j*np.array(values)))))
def rms(values):return float(np.degrees(np.sqrt(np.mean(np.square(values))))) if len(values) else None
def visit_bootstrap(rows,key):
    visits=sorted(set(r['visit'] for r in rows))
    if len(visits)<2:return None
    ss=np.array([sum(r[key]**2 for r in rows if r['visit']==v) for v in visits]);counts=np.array([sum(r['visit']==v for r in rows) for v in visits]);indices=np.random.default_rng(2026092706).integers(0,len(visits),(2000,len(visits)));values=np.degrees(np.sqrt(ss[indices].sum(axis=1)/counts[indices].sum(axis=1)));return np.quantile(values,[.025,.975]).tolist()

def main():
    plan=json.loads((HERE/'plan.json').read_text());assert len(plan['scans'])==10;summary=[];details=[];controls=[]
    phasefig,pa=plt.subplots(5,2,figsize=(14,17));rfig,ra=plt.subplots(5,2,figsize=(14,17));ddfig,da=plt.subplots(5,2,figsize=(14,17));cfofig,ca=plt.subplots(5,2,figsize=(14,17));dwellfig,wa=plt.subplots(5,2,figsize=(14,17));colors={1:'#0072B2',2:'#E69F00',3:'#009E73',4:'#CC79A7'}
    for idx,scan in enumerate(plan['scans']):
        sid=scan['session_id'];data=json.loads((HERE/(sid+'.json')).read_text());rows=data['rows'];visits={v['visit']:v for v in scan['selected']};mode_rows=[];dd=[];dwell=[]
        for row in rows:
            v=visits[row['visit']]
            for m in row['modes']:
                mode_rows.append(dict(visit=row['visit'],time_s=row['time_s'],channel=row['channel'],mode=m['mode'],qualified=m['qualified'],phase_rad=m['evaluation']['phase_rad'],R=m['evaluation']['R'],error_rad=float(wrap(m['evaluation']['phase_rad']-m['train']['phase_rad'])),tracks=v['modes'][m['mode']]['tracks']))
            if row['both_qualified']:
                a,b=row['modes'];tr=float(wrap(b['train']['phase_rad']-a['train']['phase_rad']));he=float(wrap(b['evaluation']['phase_rad']-a['evaluation']['phase_rad']));dd.append(dict(visit=row['visit'],time_s=row['time_s'],channel=row['channel'],train=tr,evaluation=he,error=float(wrap(he-tr))))
        for v in scan['selected']:
            selected=[r for r in dd if r['visit']==v['visit']]
            if selected:
                ph=[r['evaluation'] for r in selected];dwell.append(dict(visit=v['visit'],time_s=float(np.mean([r['time_s'] for r in selected])),channel=v['channel'],phase_rad=circ(ph),train_phase_rad=circ([r['train'] for r in selected]),R=float(abs(np.mean(np.exp(1j*np.array(ph))))),windows=len(selected),group=v['group'],partition=v['partition']))
        qualified=[r for r in mode_rows if r['qualified']];production_join=sum(all(any(t['published'] for t in rx) for rx in r['tracks']) for r in qualified)
        result=dict(session_id=sid,start_utc=datetime.fromtimestamp(scan['capture_utc_ns']/1e9,timezone.utc).isoformat(),rate_msps=scan['rate_hz']/1e6,visits=len(visits),windows=len(rows),mode_windows=len(mode_rows),qualified_mode_windows=len(qualified),qualified_mode_fraction=len(qualified)/len(mode_rows) if mode_rows else 0,qualified_pair_windows=len(dd),qualified_pair_dwells=len(dwell),mode_repeatability_rms_deg=rms([r['error_rad'] for r in qualified]),double_difference_rms_deg=rms([r['error'] for r in dd]),median_qualified_R=float(np.median([r['R'] for r in qualified])) if qualified else None,median_dwell_DD_R=float(np.median([r['R'] for r in dwell if r['windows']>=2])) if any(r['windows']>=2 for r in dwell) else None,both_rx_published_track_join_windows=production_join,errors=data['errors'],clipped_rows=sum(r['clipped_rows'] for r in data['audits']))
        result['mode_rms_visit_bootstrap_95_deg']=visit_bootstrap(qualified,'error_rad');result['DD_rms_visit_bootstrap_95_deg']=visit_bootstrap(dd,'error')
        result['uniquely_joined_both_rx_windows']=sum(all(sum(t['published'] for t in rx)==1 for rx in r['tracks']) for r in qualified)
        summary.append(result);details.append(dict(session_id=sid,mode_rows=mode_rows,double_differences=dd,dwell_double_differences=dwell));print(result,flush=True)
        label=f"{result['start_utc'][11:16]} UTC | {result['rate_msps']:g} MS/s | {sid[-8:]}"
        for ax in [pa.flat[idx],ra.flat[idx],da.flat[idx],ca.flat[idx],wa.flat[idx]]:ax.set_title(label);ax.set_xlabel('Time since scan start (s)');ax.grid(alpha=.2)
        for channel,color in colors.items():
            good=[r for r in qualified if r['channel']==channel];bad=[r for r in mode_rows if r['channel']==channel and not r['qualified']]
            pa.flat[idx].scatter([r['time_s'] for r in good],np.degrees([r['phase_rad'] for r in good]),s=10,color=color,label=f'CH{channel}')
            ra.flat[idx].scatter([r['time_s'] for r in bad],[r['R'] for r in bad],s=8,color='lightgray',marker='x')
            ra.flat[idx].scatter([r['time_s'] for r in good],[r['R'] for r in good],s=10,color=color,label=f'CH{channel}')
            ds=[r for r in dwell if r['channel']==channel]
            da.flat[idx].scatter([r['time_s'] for r in ds],np.degrees([r['phase_rad'] for r in ds]),s=[14+8*r['windows'] for r in ds],color=color,label=f'CH{channel}')
            stable=[r for r in ds if r['windows']>=2];wa.flat[idx].scatter([r['time_s'] for r in stable],[r['R'] for r in stable],s=[14+8*r['windows'] for r in stable],color=color,label=f'CH{channel}')
            for rx,marker in [(0,'o'),(1,'x')]:
                vs=[(v,m) for v in visits.values() if v['channel']==channel for m in v['modes']];ca.flat[idx].scatter([(v['valid_start_counter']-scan['timing']['session_start_device_sample_counter'])/scan['rate_hz'] for v,m in vs],[m['seeds'][rx]['cfo_hz']/1000 for v,m in vs],color=color,marker=marker,s=14,label=f'CH{channel} RX{rx}')
        pa.flat[idx].set(ylabel='Qualified RX1−RX0 phase (degrees)',ylim=(-185,185));ra.flat[idx].set(ylabel='Evaluation R',ylim=(-.02,1.02));da.flat[idx].set(ylabel='Visit mean double difference (degrees)',ylim=(-185,185));ca.flat[idx].set_ylabel('Raw GLRT CFO (kHz)');wa.flat[idx].set(ylabel='Across-window double-difference R',ylim=(-.02,1.02))
        if not dd:da.flat[idx].text(.5,.5,'No jointly qualified pair',ha='center',transform=da.flat[idx].transAxes)
        for group in sorted(set(r['group'] for r in dwell)-{'other-pair','single'}):
            tr=[r for r in dwell if r['group']==group and r['partition']=='train'];he=[r for r in dwell if r['group']==group and r['partition']=='held']
            if len(tr)<2 or not he:continue
            t=np.array([r['time_s'] for r in tr]);t0=t.mean();y=np.array([r['train_phase_rad'] for r in tr]);frequencies=np.linspace(-.5,.5,2001);co=np.mean(np.exp(1j*(y[None,:]-2*np.pi*frequencies[:,None]*(t-t0))),axis=1);best=int(np.argmax(abs(co)));f=float(frequencies[best]);intercept=float(np.angle(co[best]));constant=circ(y);actual=np.array([r['phase_rad'] for r in he]);pred=intercept+2*np.pi*f*(np.array([r['time_s'] for r in he])-t0)
            controls.append(dict(session_id=sid,group=group,training_visits=[r['visit'] for r in tr],held_visits=[r['visit'] for r in he],fitted_rate_hz=f,constant_held_rms_deg=rms(wrap(actual-constant)),linear_held_rms_deg=rms(wrap(actual-pred)),meaning='Random whole-visit split; sparse circular rate search can alias. Not orbital identity evidence.'))
    for fig,axes,name,title in [(phasefig,pa,'phase-time.png','Qualified receiver phase: common LO is still present; no cross-scan phase connection'),(rfig,ra,'coherence-time.png','Evaluation coherence: colored = source-qualified; gray = rejected'),(ddfig,da,'double-difference-time.png','Simultaneous two-mode double difference: common receiver phase largely cancels'),(cfofig,ca,'cfo-time.png','GLRT seed CFO: circles RX0, crosses RX1; colors identify channel'),(dwellfig,wa,'dwell-coherence-time.png','Within-visit double-difference consistency: at least two qualified windows per point')]:
        axes.flat[0].legend(fontsize=7,ncol=4);fig.suptitle(title,fontsize=13);fig.tight_layout(rect=(0,0,1,.98));fig.savefig(HERE/name,dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(15,5));x=np.arange(10);labels=[r['start_utc'][11:16] for r in summary]
    axes[0].bar(x,[r['mode_windows'] for r in summary],color='lightgray',label='Tested mode windows');axes[0].bar(x,[r['qualified_mode_windows'] for r in summary],label='Qualified mode windows');axes[0].legend(fontsize=8);axes[0].set_ylabel('Count')
    axes[1].bar(x,[r['qualified_pair_windows'] for r in summary],color='#009E73');axes[1].set_ylabel('Qualified simultaneous pair windows')
    for key,label,marker in [('mode_repeatability_rms_deg','Receiver difference','o'),('double_difference_rms_deg','Two-mode double difference','x')]:axes[2].scatter(x,[np.nan if r[key] is None else r[key] for r in summary],label=label,marker=marker)
    axes[2].set_ylabel('Training/evaluation RMS disagreement (degrees)');axes[2].legend(fontsize=8)
    for ax in axes:ax.set_xticks(x,labels,rotation=60);ax.set_xlabel('Scan start UTC (newest first)');ax.grid(axis='y',alpha=.2)
    fig.suptitle('Latest ten fully processed scans — bounded pilot-phase replay');fig.tight_layout();fig.savefig(HERE/'overview.png',dpi=170);plt.close(fig)
    (HERE/'summary.json').write_text(json.dumps(dict(scans=summary,random_visit_controls=controls),indent=2)+'\n');(HERE/'plot-data.json').write_text(json.dumps(details,indent=2)+'\n')

if __name__=='__main__':main()
