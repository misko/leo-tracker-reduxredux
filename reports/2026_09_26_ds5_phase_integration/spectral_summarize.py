from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent/'spectral-audit'
def wrap(x):return np.angle(np.exp(1j*np.asarray(x)))

def main():
    summary=[];fig,axes=plt.subplots(2,3,figsize=(13,7),constrained_layout=True)
    for row,sid in enumerate(['scan-fw-f7515a5fdb02cda5','scan-fw-888fc1e1e005ded3']):
        d=json.loads((HERE/(sid+'.json')).read_text());rows=d['rows'];origin=min(r['utc_ns'] for r in rows)
        original=wrap([r['original_held_phase']-r['original_train_phase'] for r in rows]);pivot=wrap([r['held_pivot_phase']-r['train_pivot_phase'] for r in rows])
        delays=np.array([r['delay_s'] for r in rows]);spectral=[];pair_delays=[]
        for v,s in sorted({(r['visit'],r['start_ms']) for r in rows}):
            a,b=[next(r for r in rows if r['visit']==v and r['start_ms']==s and r['mode']==m) for m in (0,1)]
            za=np.array(a['held_complex']);zb=np.array(b['held_complex']);za=za[:,0]+1j*za[:,1];zb=zb[:,0]+1j*zb[:,1]
            angles=np.angle(zb*za.conjugate());R=abs(np.mean(np.exp(1j*angles)));spectral.append(float(R));pair_delays.append(b['delay_s']-a['delay_s'])
        coherence=[r['template_coherence'] for r in d['template_overlaps']]
        scores=json.loads((HERE/(sid+'-scores.json')).read_text())['experiments']
        item=dict(session_id=sid,windows=len(rows),elapsed_s=d['elapsed_s'],delay_boundary_count=sum(r['delay_boundary'] for r in rows),median_abs_delay_ns=float(np.median(abs(delays))*1e9),median_abs_inter_mode_delay_ns=float(np.median(abs(np.array(pair_delays)))*1e9),median_tone_DD_concentration=float(np.median(spectral)),median_template_coherence=float(np.median(coherence)),maximum_template_coherence=float(max(coherence)),original_median_abs_error_deg=float(np.degrees(np.median(abs(original)))),pivot_median_abs_error_deg=float(np.degrees(np.median(abs(pivot)))),original_rms_deg=float(np.degrees(np.sqrt(np.mean(original**2)))),pivot_rms_deg=float(np.degrees(np.sqrt(np.mean(pivot**2)))),scores=[{k:e[k] for k in ('fold','sigma','arm','cfo_gain','phase_gain_vs_constant','maximum_probability_change','top_before','top_after')} for e in scores])
        summary.append(item)
        for mode,color in [(0,'tab:blue'),(1,'tab:red')]:
            rr=[r for r in rows if r['mode']==mode];axes[row,0].scatter([(r['utc_ns']-origin)/1e9 for r in rr],[r['delay_s']*1e9 for r in rr],s=10,color=color,label=f'Mode {mode}')
        axes[row,0].set_xlabel('Time since first midpoint (s)');axes[row,0].set_ylabel('Training spectral delay (ns)');axes[row,0].legend(fontsize=7)
        axes[row,1].scatter(np.degrees(abs(original)),np.degrees(abs(pivot)),s=10,alpha=.7);axes[row,1].plot([0,180],[0,180],color='gray',lw=.7);axes[row,1].set_xlabel('Original |held−train| (deg)');axes[row,1].set_ylabel('Tone pivot |held−train| (deg)')
        for offset,arm,color in [(-.15,'original_held_phase','gray'),(.15,'held_pivot_phase','tab:orange')]:
            values=[next(e['cfo_gain'] for e in scores if e['arm']==arm and e['sigma']==sigma and e['fold']==fold) for sigma,fold in [(100,0),(100,1),(200,0),(200,1)]]
            axes[row,2].bar(np.arange(4)+offset,values,width=.3,color=color,label='Original' if arm.startswith('original') else 'Tone pivot')
        axes[row,2].set_xticks(range(4),['100/f0','100/f1','200/f0','200/f1']);axes[row,2].set_ylabel('Held CFO gain (nats)');axes[row,2].set_xlabel('CFO σ (Hz) / dwell fold');axes[row,2].axhline(0,color='black',lw=.7);axes[row,2].legend(fontsize=7)
        for ax,title in zip(axes[row],['Tone-dependent response','Internal phase agreement','Association sensitivity']):ax.set_title(['09:50 UTC','12:00 UTC'][row]+'\n'+title,fontsize=11);ax.grid(alpha=.15)
    fig.savefig(HERE/'results.png',dpi=160);plt.close(fig)
    (HERE/'summary.json').write_text(json.dumps(dict(scans=summary),indent=2)+'\n')
    injected=json.loads((HERE/'single-source-injections.json').read_text())['rows'];joint=json.loads((HERE/'joint-mode-results.json').read_text())
    fig,axes=plt.subplots(1,2,figsize=(11,4),constrained_layout=True)
    for sid,label in [('scan-fw-f7515a5fdb02cda5','09:50'),('scan-fw-888fc1e1e005ded3','12:00')]:
        for source in (0,1):
            rr=[r for r in injected if r['session_id']==sid and r['source_mode']==source and r['extracted_mode']!=source]
            axes[0].plot([-20,0,20,40],[r['held_R'] for r in rr],marker='o',label=f'{label}, source {source}')
    axes[0].set_xticks([-20,0,20,40],['−20','0','20','Noiseless']);axes[0].set_xlabel('Synthetic single-source SNR (dB)');axes[0].set_ylabel('Held R at absent-mode template');axes[0].set_title('High coherence can be leakage',fontsize=11);axes[0].legend(fontsize=7)
    labels=[];values=[];colors=[]
    for r in joint['real']:
        labels.append(str(r['visit'])+'\n'+str(r['start_ms'])+' ms');values.append(1e6*min(m['incremental_held_fraction'] for m in r['metrics']));colors.append('tab:blue' if r['start_ms']==0 else 'tab:orange')
    axes[1].bar(np.arange(len(values)),values,color=colors);axes[1].set_xticks(np.arange(len(values)),labels,fontsize=7);axes[1].axhline(0,color='black',lw=.7);axes[1].set_ylabel('Minimum held improvement across RX/modes (ppm)');axes[1].set_title('Real joint-mode support varies within a dwell',fontsize=11)
    for ax in axes:ax.grid(alpha=.2)
    fig.savefig(HERE/'leakage-and-joint-support.png',dpi=160);plt.close(fig)
    print(json.dumps([{k:v for k,v in s.items() if k!='scores'} for s in summary],indent=2))

if __name__=='__main__':main()
