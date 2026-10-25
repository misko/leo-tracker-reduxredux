"""Saved six-vector diagnostics only; no propagation, scores or fitting."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
PERIOD=1/4.4e-6


def read(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def classify(order,truth):
    if not order.get('proved'):return 'unresolved numerically'
    if order.get('winner_kind')=='unresolved':return 'near-null comparator'
    if truth.get('norad')==order.get('winner_norad'):return 'generating physical'
    return 'other physical'


def main():
    seal=read(HERE/'RF_seal.json')
    assert all(sha(p)==h for p,h in seal['files'].items())
    execution=read(HERE/'execution.json');rows=[];generated=[]
    for case in ['DS24-0010','DS24-0011']:
        for trial in range(3):
            directory=HERE/case/f'trial{trial}'
            truth=read(directory/'truth.json') if (directory/'truth.json').exists() else {}
            if truth:generated.append(dict(case=case,trial=trial,kind=truth['kind'],norad=truth['norad']))
            for arm in ['c0','fitted_c']:
                result=read(directory/arm/'result.json') if (directory/arm/'result.json').exists() else dict(status='unavailable',error='missing slot')
                screen=read(directory/(arm+'_ordinary_screen.json')) if (directory/(arm+'_ordinary_screen.json')).exists() else {}
                c0screen=read(directory/'c0_ordinary_screen.json') if (directory/'c0_ordinary_screen.json').exists() else {}
                index=truth.get('candidate_index');ranking=screen.get('ranked_visible_indices',[])
                physical=truth.get('kind')=='physical';rank=(ranking.index(index)+1) if physical and index in ranking else None
                actual=(index in c0screen.get('candidate_indices',[])) if physical else None
                true_row=next((x for x in result.get('candidates',[]) if x['norad']==truth.get('norad')),None)
                if true_row is None:true_row=result.get('label_available_diagnostic')
                true_row=true_row or {}
                ordinary=result.get('ordinary_order',{});available=result.get('label_available_order',{})
                rows.append(dict(case=case,trial=trial,arm=arm,kind=truth.get('kind'),generating_norad=truth.get('norad'),status=result['status'],
                    matching_law=arm=='c0',same_observation_fitted_sensitivity=arm!='c0',own_screen_true_rank=rank,
                    generating_label_in_FIXED_c0_top8=actual,ordinary_outcome=classify(ordinary,truth),available_label_outcome=classify(available,truth),
                    ordinary_order_proved=ordinary.get('proved',False),available_order_proved=available.get('proved',False),
                    ordinary_winner_norad=ordinary.get('winner_norad'),available_winner_norad=available.get('winner_norad'),
                    ordinary_minimum_log_evidence_margin=ordinary.get('minimum_log_evidence_margin'),
                    true_candidate_objective=true_row.get('objective'),near_null_objective=result.get('null',{}).get('objective'),
                    true_candidate_absolute_precision=true_row.get('numerically_qualified',False),
                    scored_ordinary_physical_candidates=len(result.get('candidates',[])),ordinary_candidate_slots=len(c0screen.get('candidate_indices',[])),
                    error=result.get('error'),seconds=result.get('seconds')))
    out=HERE/'report';out.mkdir()
    with (out/'outcomes.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    physical=[r for r in rows if r['kind']=='physical'];names=[]
    for ix,row in enumerate([x for x in physical if x['arm']=='c0']):
        pair=[x for x in physical if x['case']==row['case'] and x['trial']==row['trial']]
        names.append(row['case'][-4:]+' / '+str(row['generating_norad']))
        for delta,arm,color in [(-.09,'c0','#176da3'),(.09,'fitted_c','#c77b30')]:
            value=next(x for x in pair if x['arm']==arm)
            if value['own_screen_true_rank'] is not None:axes[0].plot(ix+delta,value['own_screen_true_rank'],'o',color=color,label=arm if ix==0 else None)
    axes[0].axhline(8.5,color='black',ls='--',lw=1,label='Top8 boundary')
    axes[0].set_xticks(range(len(names)),names,rotation=25,ha='right');axes[0].set(ylabel='Generating-label rank (lower is better)',yscale='log',title='Ordinary full-catalogue nomination\nFitted screen is diagnostic; exact pool stays c0 top8')
    axes[0].legend(fontsize=8);axes[0].grid(alpha=.2)
    colors={'generating physical':'#d1e6f3','near-null comparator':'#eed9b7','other physical':'#edc6c6','unresolved numerically':'#eeeeee'}
    axes[1].set_xlim(0,2);axes[1].set_ylim(6,0)
    for column,arm in enumerate(['c0','fitted_c']):
        for index,row in enumerate(x for x in rows if x['arm']==arm):
            ordinary=row['ordinary_outcome'];available=row['available_label_outcome']
            label=row['case'][-4:]+' '+('null' if row['kind']=='near_null' else str(row['generating_norad']))+'\n'+ordinary+' → '+available
            axes[1].add_patch(plt.Rectangle((column,index),1,1,color=colors[available],ec='white'))
            axes[1].text(column+.5,index+.5,label,ha='center',va='center',fontsize=7)
    axes[1].set_xticks([.5,1.5],['c0: matching law','fitted-c: off-law sensitivity']);axes[1].set_yticks([])
    axes[1].set_title('Ordinary → label-available finite-pool result\nNo operational acceptance or population error-rate claim')
    fig.savefig(out/'nomination_and_evidence.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(2,3,figsize=(13,7),layout='constrained')
    for row,case in enumerate(['DS24-0010','DS24-0011']):
        with np.load(HERE/case/'context.npz') as context:
            times=context['times_s'];mu=context['c0_radio_mean_Hz'];nullmean=context['null_mean_Hz'];factor=context['null_factor_Hz'];noise=context['c0_covariance_Hz2']
        sd=np.sqrt(np.diag(noise+factor@factor.T))
        for trial in range(3):
            p=HERE/case/f'trial{trial}'
            if not (p/'truth.json').exists():continue
            truth=read(p/'truth.json')
            with np.load(p/'observations.npz') as obs:y=obs['values_Hz']
            ax=axes[row,trial];ax.fill_between(times,-2*sd,2*sd,color='#cdb587',alpha=.3,label='Declared near-null marginal ±2 SD')
            ax.plot(times,y+truth['alias']*PERIOD-mu-nullmean,'.-',color='#176da3',label='Synthetic observations, known generating gauge')
            ax.axhline(0,color='black',lw=.6);ax.grid(alpha=.2)
            ax.set(title=case+' '+(str(truth['norad']) if truth['kind']=='physical' else 'near-null'),xlabel='Scan time (s)',ylabel='CFO minus fixed pair midpoint (Hz)')
            if row==0 and trial==0:ax.legend(fontsize=7)
    fig.suptitle('Close synthetic controls: original c0 exogenous background removed\nKnown draw alias only for this visualization; no alias chosen from a fit; bands not calibrated identity confidence')
    fig.savefig(out/'synthetic_controls.png',dpi=150);plt.close(fig)
    summary=dict(rows=rows,generated_vectors=generated,planned_vectors=6,planned_arm_trial_slots=12,
        worker_seconds=execution['worker_seconds'],wall_seconds=execution['wall_seconds'],
        c0_matching_law=True,fitted_c_same_vector_off_law_sensitivity=True,
        physical_top8_recall=sum(x['generating_label_in_FIXED_c0_top8'] is True for x in rows if x['arm']=='c0' and x['kind']=='physical'),
        physical_trials=sum(x['kind']=='physical' for x in generated),
        complete_arm_trials=sum(x['status']=='complete' for x in rows),new_position_fits=0,operational_identity_assignments=0,GPS_used=False)
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    outputs=[Path(__file__),out/'outcomes.csv',out/'summary.json',out/'nomination_and_evidence.png',out/'synthetic_controls.png']
    (out/'seal.json').write_text(json.dumps(dict(files={str(p):sha(p) for p in outputs},RF_seal_sha256=sha(HERE/'RF_seal.json')),indent=2)+'\n')


if __name__=='__main__':main()
