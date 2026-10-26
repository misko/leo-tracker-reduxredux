"""Readable saved-only primary/single-source comparison; no selector or graph runs."""
import json
from collections import Counter
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import continuity as c
import experiment as e
import report as r

HERE=Path(__file__).resolve().parent
OUT=HERE/'report02'
METHODS=('original_winners','cfo_only','epoch_cfo')
TITLES=('Original winners','CFO-only paths','Epoch + CFO paths')


def verify(path):
    seal=json.loads(path.read_text())
    for file,digest in seal['files'].items():
        if e.sha(file)!=digest:raise ValueError('sealed artifact changed: '+file)


def primary_figures(port,summary):
    fig,axes=plt.subplots(2,4,figsize=(15,7.6),layout='constrained',sharex=True,sharey='row')
    for column,episode in enumerate(port['episodes']):
        name=episode['name'];windows=episode['windows']
        by_candidate={n['candidate_id']:w for w in windows for n in w['candidates']}
        for row,quantity in enumerate(('cfo','epoch')):
            ax=axes[row,column]
            for w in [w for w in windows if w['receiver_id']=='0']:
                tr=json.loads((e.OLD/'slots'/f"{name}_{round(w['window_start_counter']/e.RATE):02}.json").read_text())['sources'][0]
                for node in w['candidates']:
                    value=float(c.circular(node['cfo_hz']-(tr['cfo0']+tr['rate']*w['time_s']),c.SETTINGS['cfo_period_hz'])) if quantity=='cfo' else float(c.circular(node['global_epoch_samples']-127,e.RATE/750))
                    ax.scatter(w['time_s'],value,color='.8',s=10,zorder=1)
            for rx,marker in (('0','o'),('1','x')):
                for method in ('original_winners','cfo_only'):
                    selected=json.loads((HERE/'selections'/f'{name}_RX{rx}_{method}.json').read_text())
                    for pi,path in enumerate(selected['paths']):
                        xs=[];ys=[]
                        for node in path['nodes']:
                            w=by_candidate[node['candidate_id']];t=w['time_s'];xs.append(t)
                            ys.append(float(c.circular(node['cfo_hz']-(100000+200*t),c.SETTINGS['cfo_period_hz'])) if quantity=='cfo' else float(c.circular(node['global_epoch_samples']-127,e.RATE/750)))
                        ax.plot(xs,ys,color='black' if method=='original_winners' else ('#1769a3','#b15d29')[pi],
                            linestyle=':' if method=='original_winners' else '-',alpha=.6 if method=='original_winners' else .85,
                            marker=marker,markersize=3,linewidth=.8 if method=='original_winners' else 1.2)
            ts=np.arange(16)+.01
            ax.axhline(0,color='.4',linestyle='--',linewidth=.8)
            ax.plot(ts,3000-400*ts if quantity=='cfo' else np.full(16,0 if name.startswith('coincident') else 684),
                    color='.4',linestyle='-.',linewidth=.8)
            ax.set_yscale('symlog',linthresh=300 if quantity=='cfo' else 3)
            ax.set_ylim((-120000,120000) if quantity=='cfo' else (-7000,7000))
            ax.set_yticks([-100000,-1000,0,1000,100000] if quantity=='cfo' else [-1000,-10,0,10,1000])
            ax.set_yticklabels(['−100k','−1k','0','1k','100k'] if quantity=='cfo' else ['−1000','−10','0','10','1000'])
            ax.set_xticks([0,5,10,15]);ax.grid(alpha=.2);ax.tick_params(labelsize=9)
            if row==0:ax.set_title(name.replace('_sampled_deployed','\nDeployed sampled').replace('_continuous','\nContinuous'),fontsize=10)
            if row==1:ax.set_xlabel('Synthetic seconds')
            if column==0:ax.set_ylabel('Circular CFO − known A (Hz)' if quantity=='cfo' else 'Circular epoch − known A (samples)')
    fig.legend(handles=[Line2D([],[],color='black',linestyle=':',label='Original winners'),
        Line2D([],[],color='#1769a3',label='Path 1'),Line2D([],[],color='#b15d29',label='Path 2'),
        Line2D([],[],marker='o',color='.8',linestyle='',label='RX0 candidate pool'),
        Line2D([],[],color='.4',linestyle='--',label='Known A'),Line2D([],[],color='.4',linestyle='-.',label='Known B')],
        loc='outside upper center',ncol=6,fontsize=9)
    fig.supxlabel('CFO-only and epoch+CFO select identical paths. Both receivers shown (RX0: o; RX1: ×). Truth is evaluation only.',fontsize=10)
    fig.savefig(OUT/'primary_paths.png',dpi=170);plt.close(fig)
    rows=summary['comparisons'];fig,axes=plt.subplots(1,2,figsize=(12,4.8),layout='constrained')
    for ax,key,title,limit in ((axes[0],'unique_selected_windows','Unique receiver-window coverage',32),
                              (axes[1],'selected_joint_source_coverage','Known-source proximity coverage',64)):
        for j,method in enumerate(METHODS):
            selected=[x for x in rows if x['method']==method]
            ax.bar(np.arange(4)+(j-1)*.24,[x[key] for x in selected],width=.23,label=TITLES[j])
        ax.set_xticks(range(4),[x['name'].replace('_sampled_deployed','\nsampled').replace('_continuous','\ncontinuous') for x in port['episodes']],fontsize=9)
        ax.axhline(limit,color='.6',linestyle=':');ax.set_ylim(0,limit+3);ax.set_ylabel('Unique slots');ax.set_title(title)
        ax.grid(axis='y',alpha=.2)
    h,l=axes[0].get_legend_handles_labels();fig.legend(h,l,loc='outside upper center',ncol=3)
    fig.supxlabel('Source proximity slots are not independent measurements, physical source counts or validated identities.',fontsize=10)
    fig.savefig(OUT/'coverage.png',dpi=170);plt.close(fig)


def single_report():
    root=HERE/'single_application';verify(root/'RF_seal.json')
    port=json.loads((root/'rows.json').read_text());windows=port['windows']
    byid={n['candidate_id']:(w,n) for w in windows for n in w['candidates']}
    execution=json.loads((root/'execution.json').read_text());method_rows=[];path_rows=[];graphs={};paths={}
    for record in execution['records']:
        if record['status']!='complete':
            method_rows.append(dict(receiver=record['receiver_id'],method=record['method'],status=record['status']));continue
        selected=json.loads(Path(record['selection_file']).read_text());graph=json.loads(Path(record['graph_file']).read_text())
        paths[(record['receiver_id'],record['method'])]=selected;graphs[(record['receiver_id'],record['method'])]=graph
        used=Counter();quality=Counter();assigned=0;graph_windows=set();hits=set()
        for pi,(path,g) in enumerate(zip(selected['paths'],graph)):
            cf=[];ep=[];near=0;ranks=Counter();ratios=[]
            for node in path['nodes']:
                w,n=byid[node['candidate_id']];used[w['window_id']]+=1
                delta_f=float(c.circular(n['cfo_hz']-(100000+200*w['time_s']),c.SETTINGS['cfo_period_hz']))
                delta_e=float(c.circular(n['global_epoch_samples']-127,e.RATE/750))
                cf.append(delta_f);ep.append(delta_e);ranks[n['candidate_rank']]+=1
                ratios.append(n['margin']/max(x['margin'] for x in w['candidates']))
                if abs(delta_f)<=450 and abs(delta_e)<=3:near+=1;hits.add(w['window_id'])
            for t in g['tracks']:
                quality[t['quality_status']]+=1
                graph_windows.update(t['observation_ids'])
            assigned+=g['assigned']
            path_rows.append(dict(receiver=int(record['receiver_id']),method=record['method'],path=pi,
                candidate_hypotheses=len(path['nodes']),score=path['score'],joint_near_injected_source=near,
                median_CFO_error_Hz=float(np.median(cf)),max_abs_CFO_error_Hz=float(max(abs(np.array(cf)))),
                median_epoch_error_samples=float(np.median(ep)),max_abs_epoch_error_samples=float(max(abs(np.array(ep)))),
                median_margin_ratio=float(np.median(ratios)),rank_histogram=json.dumps(dict(ranks)),
                graph_assigned_candidate_hypotheses=g['assigned'],
                graph_statuses=json.dumps([t['quality_status'] for t in g['tracks']]),
                graph_RMS_Hz=json.dumps([t['residual_rms_hz'] for t in g['tracks']]),
                graph_flags=json.dumps([t['diagnostics']['quality_flags'] for t in g['tracks']])))
        method_rows.append(dict(receiver=int(record['receiver_id']),method=record['method'],status='complete',
            path_hypotheses=len(selected['paths']),selected_candidate_hypotheses=selected['candidate_hypotheses_selected'],
            unique_receiver_windows=selected['unique_receiver_windows'],shared_windows=sum(v>1 for v in used.values()),
            joint_near_injected_source_windows=len(hits),graph_candidate_assignments=assigned,
            unique_graph_windows=len(graph_windows),graph_no_structure_detected=quality['no_structure_detected'],
            graph_structure_flagged=quality['structure_flagged'],graph_insufficient_support=quality['insufficient_support']))
    r.table(OUT/'single_methods.csv',method_rows);r.table(OUT/'single_paths.csv',path_rows)
    same={rx:[[n['candidate_id'] for n in p['nodes']] for p in paths[(rx,'cfo_only')]['paths']]==
             [[n['candidate_id'] for n in p['nodes']] for p in paths[(rx,'epoch_cfo')]['paths']] for rx in ('0','1')}
    fig,axes=plt.subplots(2,3,figsize=(12,7),layout='constrained',sharex=True,sharey='row')
    for col,method in enumerate(METHODS):
        for ri,quantity in enumerate(('cfo','epoch')):
            ax=axes[ri,col]
            for w in [w for w in windows if w['receiver_id']=='0']:
                for node in w['candidates']:
                    value=float(c.circular(node['cfo_hz']-(100000+200*w['time_s']),c.SETTINGS['cfo_period_hz'])) if quantity=='cfo' else float(c.circular(node['global_epoch_samples']-127,e.RATE/750))
                    ax.scatter(w['time_s'],value,color='.8',s=12)
            for rx,marker in (('0','o'),('1','x')):
                for pi,path in enumerate(paths[(rx,method)]['paths']):
                    xs=[];ys=[]
                    for node in path['nodes']:
                        w,n=byid[node['candidate_id']];t=w['time_s'];xs.append(t)
                        ys.append(float(c.circular(n['cfo_hz']-(100000+200*t),c.SETTINGS['cfo_period_hz'])) if quantity=='cfo' else float(c.circular(n['global_epoch_samples']-127,e.RATE/750)))
                    ax.plot(xs,ys,color=('#1769a3','#b15d29')[pi],marker=marker,markersize=3,linewidth=1)
            ax.axhline(0,color='black',linestyle='--',linewidth=.8);ax.grid(alpha=.2)
            ax.set_yscale('symlog',linthresh=3);ax.set_xticks([0,5,10,15,20,23])
            if ri==0:ax.set_title(TITLES[col])
            if ri==1:ax.set_xlabel('Synthetic seconds')
            if col==0:ax.set_ylabel('Circular CFO error (Hz)' if quantity=='cfo' else 'Circular epoch error (samples)')
    fig.legend(handles=[Line2D([],[],color='#1769a3',label='Path 1'),Line2D([],[],color='#b15d29',label='Path 2'),
        Line2D([],[],marker='o',linestyle='',color='.8',label='RX0 candidate pool'),
        Line2D([],[],color='black',linestyle='--',label='ONE injected source (evaluation only)')],loc='outside upper center',ncol=4,fontsize=9)
    fig.supxlabel('Both controls retain an extra path hypothesis from one signal. None of the main or secondary graph tracks qualifies.',fontsize=10)
    fig.savefig(OUT/'single_source_paths.png',dpi=170);plt.close(fig)
    return dict(execution=execution,methods=method_rows,paths=path_rows,
                epoch_and_CFO_paths_identical=same,one_injected_source=True)


def main():
    OUT.mkdir(exist_ok=False);verify(HERE/'report/seal.json')
    port=json.loads((HERE/'prepared/synthetic_rows.json').read_text())
    summary=json.loads((HERE/'report/summary.json').read_text())
    primary_figures(port,summary);single=single_report()
    e.write(OUT/'summary.json',dict(primary_report_seal_sha256=e.sha(HERE/'report/seal.json'),
        primary_comparisons=summary['comparisons'],single_control=single,new_scientific_runs=False))
    files=[Path(__file__),*[p for p in OUT.iterdir() if p.is_file()]]
    e.write(OUT/'seal.json',dict(files={str(p):e.sha(p) for p in files},saved_artifacts_only=True,
        primary_RF_seal_sha256=e.sha(HERE/'RF_seal.json'),single_RF_seal_sha256=e.sha(HERE/'single_application/RF_seal.json')))
    print(json.dumps(single,indent=2))


if __name__=='__main__':main()
