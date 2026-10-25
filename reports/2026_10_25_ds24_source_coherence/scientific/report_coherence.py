"""Saved-artifact report only: no propagation, fitting, or evidence integration."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent
RUN=HERE/'run02'
OUT=HERE/'report'
ARMS=('c0','fitted_c')
FAMILIES=('whole_physical','whole_polynomial','split','piecewise_polynomial')
LABELS=('Whole physical W','Whole polynomial W','Physical portion + polynomial rest','Two polynomial pieces')
read=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(name,value):
    with (OUT/name).open('x') as stream:json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')


def table(name,rows):
    with (OUT/name).open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def main():
    seal=read(RUN/'RF_seal.json')
    if not seal['all_selected_terminal']:raise ValueError('terminal RF seal required')
    for path,digest in seal['files'].items():
        if sha(path)!=digest:raise ValueError('bound file changed: '+path)
    OUT.mkdir(exist_ok=False)
    results={arm:read(RUN/arm/'result.json') for arm in ARMS}
    if any(row['status']!='complete' or len(row['models'])!=11 or len(row['classes'])!=4 for row in results.values()):
        raise ValueError('report expects this complete22cell/eightclass result; never replace a missing outcome')
    class_rows=[];cell_rows=[];summary={}
    for arm,result in results.items():
        group={row['family']:row for row in result['classes']}
        reference=group['split']['window_log_evidence']
        tail=result['remote_guard']
        for family in FAMILIES:
            row=group[family]
            class_rows.append(dict(arm=arm,family=family,class_prior=row['class_prior'],normalized_cells=row['normalized_cells'],
                lower_log_evidence=row['lower_log_evidence'],upper_log_evidence=row['upper_log_evidence'],
                window_log_evidence=row['window_log_evidence'],window_objective=row['window_objective'],
                lower_minus_split_window=row['lower_log_evidence']-reference,
                upper_minus_split_window=row['upper_log_evidence']-reference,
                full_absolute_objective_width=2*(row['upper_log_evidence']-row['lower_log_evidence']),
                globally_ordered_winner=result['ordering'].get('winner'),identity_assigned=False,portion_adopted=False))
        for row in result['models']:
            bound=row['bounds'];full_upper=float(np.logaddexp(bound['upper_log_integral'],tail))
            cell_rows.append(dict(arm=arm,name=row['name'],family=row['family'],cut=row['cut'],allocation=row['allocation'],
                within_class_prior=float(np.exp(row['log_within_prior'])),window_objective32=-2*row['log_integral32'],
                window_objective64=-2*row['log_integral64'],quadrature_difference_objective=row['quadrature_difference_objective'],
                independent_quadrature_passed=row['independent_quadrature_passed'],
                global_lower_log_evidence=bound['lower_log_integral'],global_upper_log_evidence=full_upper,
                local_envelope_panels=bound['panels'],full_absolute_objective_width=2*(full_upper-bound['lower_log_integral']),
                full_absolute_precision_1e_3=2*(full_upper-bound['lower_log_integral'])<=1e-3,
                within_class_window_weight=group[row['family']]['within_class_window_weights'][row['name']],
                all100_IDs_scored=True,portion_adopted=False))
        summary[arm]=dict(ordering=result['ordering'],classes=result['classes'],
            D_replay=read(RUN/arm/'D_replay.json'),whole_polynomial_replay=read(RUN/arm/'replay.json'),
            remote_guard=read(RUN/arm/'remote_guard.json'),scientific_worker_seconds=result['scientific_worker_seconds'],
            maximum_quadrature_difference_objective=max(row['quadrature_difference_objective'] for row in result['models']))
    table('class_table.csv',class_rows);table('cell_table.csv',cell_rows)
    execution=read(RUN/'execution.json')
    write('summary.json',dict(arms=summary,execution=execution,selected_model_contexts=22,selected_class_contexts=8,
        absolute_precision_qualified_cells=sum(row['full_absolute_precision_1e_3'] for row in cell_rows),
        source_scope='conditional model scores; no calibrated identity posterior or partial-source admission',
        source_sha256=sha(__file__),RF_seal_sha256=sha(RUN/'RF_seal.json')))

    # Every finite bound, including remote-phase upper mass, remains visible.
    fig,axes=plt.subplots(1,2,figsize=(13,5.2),sharey=True,layout='constrained')
    for ax,arm in zip(axes,ARMS):
        rows=[row for row in class_rows if row['arm']==arm]
        reference=next(row['window_log_evidence'] for row in rows if row['family']=='split')
        for index,row in enumerate(rows):
            color='#00796b' if row['family']=='split' else '#65758b'
            lo,hi=row['lower_minus_split_window'],row['upper_minus_split_window']
            point=row['window_log_evidence']-reference
            ax.hlines(index,lo,hi,color=color,lw=5,alpha=.65)
            ax.plot([lo,hi],[index,index],'|',color=color,ms=13)
            ax.plot(point,index,'o',color=color,ms=5)
            ax.annotate(f'[{lo:.2f}, {hi:.2f}]',(hi,index),xytext=(4,9),textcoords='offset points',fontsize=8)
        ax.axvline(0,color='black',lw=.7,ls=':')
        ax.set_xscale('symlog',linthresh=5)
        ax.set_yticks(range(4),LABELS);ax.set_ylim(3.5,-.7)
        ax.tick_params(axis='y',labelleft=True)
        ax.set_xlabel('log Z − split-window log Z (symlog axis)')
        margin=results[arm]['ordering']['minimum_log_evidence_margin']
        ax.set_title(('c = 0' if arm=='c0' else 'Fitted c')+f'\nSplit class: conservative log-score margin ≥ {margin:.3f}')
        ax.grid(axis='x',alpha=.2)
    fig.suptitle('Full-domain conditional model-score bounds\nIntervals include remote phase mass; dots are window estimates. Not identity probabilities.',fontsize=12)
    fig.savefig(OUT/'class_evidence_bounds.png',dpi=180);plt.close(fig)

    fig,axes=plt.subplots(1,2,figsize=(12,4.7),layout='constrained')
    labels=['14 prefix','14 suffix','21 prefix','21 suffix','29 prefix','29 suffix']
    for ax,arm in zip(axes,ARMS):
        split=next(row for row in results[arm]['classes'] if row['family']=='split')
        values=[split['within_class_window_weights']['cut'+str(cut)+'_'+allocation]
            for cut in (14,21,29) for allocation in ('prefix','suffix')]
        bars=ax.bar(range(6),values,color=['#00796b','#b9c4d0']*3)
        for bar,value in zip(bars,values):
            text=f'{100*value:.2f}%' if value>=1e-6 else '< 0.0001%'
            ax.annotate(text,(bar.get_x()+bar.get_width()/2,bar.get_height()),xytext=(0,5),textcoords='offset points',ha='center',fontsize=8)
        ax.set_ylim(0,.72);ax.set_xticks(range(6),labels,rotation=35,ha='right')
        ax.set_ylabel('Within-split-class window weight')
        ax.set_title('c = 0' if arm=='c0' else 'Fitted c');ax.grid(axis='y',alpha=.2)
    fig.suptitle('Allocation diagnostics within the computational window\nSix choices have equal prior 1/6; weights are not calibrated identity or support probabilities.',fontsize=12)
    fig.savefig(OUT/'split_window_weights.png',dpi=180);plt.close(fig)
    files={str(path):sha(path) for path in sorted(OUT.iterdir()) if path.is_file()}
    files[str(Path(__file__))]=sha(__file__)
    write('report_seal.json',dict(files=files,RF_seal_sha256=sha(RUN/'RF_seal.json'),
        new_propagation_calls=0,new_evidence_integrals=0,new_fits=0))
    print(json.dumps(dict(report=str(OUT),classes=len(class_rows),cells=len(cell_rows),
        cumulative_scientific_worker_seconds=execution['cumulative_scientific_worker_seconds'])))


if __name__=='__main__':main()
