"""Saved-only precision-block contrasts; geography requires separate release."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
OLD=Path('/srv/bulk/leo/research/ds24-cfo-precision-factorial-r01/solver')
VI=Path('/srv/bulk/leo/research/ds24-complete-owner-refinement-r01/position')
CASES=('DS24-0010','DS24-0011');ARMS=('c0','fitted_c');CELLS=('00','10','01','11')
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(path,value):
    with Path(path).open('x') as stream:json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')


def csv_write(path,rows):
    keys=list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=keys);writer.writeheader();writer.writerows(rows)


def verify(path):
    for name,h in read(path)['files'].items():
        if sha(name)!=h:raise ValueError('bound file changed: '+name)


def contrasts(points):
    if any(points.get(cell) is None for cell in CELLS):return dict(complete=False,reason='missing_cell_retained')
    x={k:np.asarray(points[k],float) for k in CELLS}
    if any(v.shape!=(2,) or not np.isfinite(v).all() for v in x.values()):raise ValueError('finite2D endpoints required')
    a=x['10']-x['00'];b=x['11']-x['01'];c=x['01']-x['00'];d=x['11']-x['10']
    values=dict(noise_at_original_prior=a,noise_at_refined_prior=b,prior_at_original_noise=c,prior_at_refined_noise=d,
        interaction=x['11']-x['10']-x['01']+x['00'],symmetric_noise=(a+b)/2,symmetric_prior=(c+d)/2,total=x['11']-x['00'])
    closure=float(np.linalg.norm(values['symmetric_noise']+values['symmetric_prior']-values['total']))
    if closure>1e-12:raise ValueError('signed block decomposition does not close')
    return dict(complete=True,vectors_km={k:v.tolist() for k,v in values.items()},
        norms_m={k:float(np.linalg.norm(v)*1000) for k,v in values.items()},vector_closure_error_km=closure,
        displacement_norms_are_not_additive=True,observations='original_CFO_only')


def outcome_rows():
    rows=[];execution=read(HERE/'execution.json')
    for case in CASES:
        for arm in ARMS:
            for cell,sourcecell in (('00','00'),('11','01')):
                source=OLD/case/arm/(sourcecell+'_result.json');row=read(source)
                row.update(cell=cell,noise_origin='original' if cell=='00' else 'corrected',
                    prior_origin='original' if cell=='00' else 'corrected',new_fit=False,
                    source_path=str(source),source_sha256=sha(source),original_factorial_source_cell=sourcecell)
                rows.append(row)
    for slot in execution['all8_slots']:rows.append(dict(slot,new_fit=True))
    for row in rows:
        if row['status']=='complete':
            x=row.pop('endpoint_east_north_km');row.update(east_km=x[0],north_km=x[1])
    for case in CASES:
        for cell in CELLS:
            pair=[r for r in rows if r['case']==case and r['cell']==cell]
            passed=len(pair)==2 and all(r['status']=='complete' and r['original_single_arm_valid'] and
                r['final_phase_change_s']<=.01 and r['original_accepted_IDs_lost']==0 for r in pair)
            for row in pair:row['paired_research_guards_pass']=passed
    return sorted(rows,key=lambda r:(r['case'],r['arm'],CELLS.index(r['cell'])))


def rf():
    verify(HERE/'RF_seal.json');out=HERE/'rf_report';out.mkdir(exist_ok=False)
    rows=outcome_rows();comparisons=[]
    for case in CASES:
        for arm in ARMS:
            rr={r['cell']:r for r in rows if r['case']==case and r['arm']==arm}
            points={c:[rr[c]['east_km'],rr[c]['north_km']] if rr[c]['status']=='complete' else None for c in CELLS}
            comparisons.append(dict(case=case,arm=arm,**contrasts(points)))
    csv_write(out/'outcomes.csv',rows);write(out/'contrasts.json',comparisons)
    write(out/'summary.json',dict(rows=rows,contrasts=comparisons,new_slots=8,reused_diagonal_slots=8,
        new_completed=sum(r['new_fit'] and r['status']=='complete' for r in rows),
        cumulative_worker_seconds=read(HERE/'execution.json')['cumulative_worker_seconds'],GPS_used=False,
        objective_kind='same_conditional_Gaussian_not_VI_ELBO',operational_policy='original_reference'))
    fig,axes=plt.subplots(2,2,figsize=(10.6,8),layout='constrained')
    for ax,q in zip(axes.ravel(),comparisons):
        if not q['complete']:ax.text(.5,.5,'Incomplete factorial',ha='center');continue
        rr={r['cell']:r for r in rows if r['case']==q['case'] and r['arm']==q['arm']}
        origin=np.array([rr['00']['east_km'],rr['00']['north_km']])
        for cell in CELLS:
            p=(np.array([rr[cell]['east_km'],rr[cell]['north_km']])-origin)*1000
            ax.scatter(*p,s=35);ax.annotate(cell,p,xytext=(5,5),textcoords='offset points')
        a=np.asarray(q['vectors_km']['symmetric_noise'])*1000;b=np.asarray(q['vectors_km']['symmetric_prior'])*1000
        ax.annotate('',a,xytext=[0,0],arrowprops=dict(arrowstyle='->',color='#176b8b',lw=2))
        ax.annotate('',a+b,xytext=a,arrowprops=dict(arrowstyle='->',color='#b06624',lw=2))
        ax.plot([0,(a+b)[0]],[0,(a+b)[1]],'--',color='.4',lw=1)
        ax.set_title(q['case']+' · '+('c=0' if q['arm']=='c0' else 'fitted c'))
        ax.set_xlabel('East displacement from00 (m)');ax.set_ylabel('North displacement from00 (m)');ax.grid(alpha=.2);ax.margins(.22)
    fig.suptitle('Original CFO: noise versus nuisance-prior precision\nBlue: symmetric noise vector; orange: symmetric prior vector; norms are not additive',fontsize=12)
    fig.savefig(out/'block_vectors.png',dpi=170);plt.close(fig)
    write(out/'seal.json',dict(files={str(p):sha(p) for p in list(out.iterdir())+[Path(__file__),HERE/'RF_seal.json'] if p.is_file()}))
    print(json.dumps(comparisons,indent=2))


def latlon(x):return 37.906+x[1]/111.,-122.545+x[0]/(111.32*math.cos(math.radians(37.906)))


def distance(a,b):
    la,lo,lb,lp=map(math.radians,(*a,*b));h=math.sin((lb-la)/2)**2+math.cos(la)*math.cos(lb)*math.sin((lp-lo)/2)**2
    return 6371.0088*2*math.asin(math.sqrt(min(1.,max(0.,h))))


def geography(reference):
    verify(HERE/'RF_seal.json');verify(HERE/'rf_report/seal.json')
    if read(HERE/'protocol.json')['files'][str(Path(__file__))]!=sha(__file__):raise ValueError('evaluator changed after freeze')
    audit=read(ROOT/'audit/mechanism_terminal.json')
    if not audit['all_passed'] or not audit.get('RF_ready_for_separate_geographic_evaluation') or audit['RF_seal_sha256']!=sha(HERE/'RF_seal.json'):
        raise ValueError('exact passing terminal audit required')
    out=HERE/'geographic';out.mkdir(exist_ok=False);rows=[]
    for row in read(HERE/'rf_report/summary.json')['rows']:
        original=read(VI/row['case']/'original'/row['arm']/'raw_endpoint.json')['summary']['endpoint_east_north_km']
        baseline=distance(latlon(original),reference)
        error=distance(latlon([row['east_km'],row['north_km']]),reference) if row['status']=='complete' else None
        rows.append(dict(row,raw_position_error_km=error,operational_reference_error_km=baseline,
            operational_policy_error_km=baseline,operational_policy='exact_original_reference'))
    csv_write(out/'outcomes.csv',rows);write(out/'summary.json',dict(rows=rows,reference_latlon=reference,new_fits=0,
        root_release='explicit coordinator message after passing RF audit',new_endpoint_slots=8,reused_diagonal_slots=8))
    fig,axes=plt.subplots(2,2,figsize=(10.6,8),sharey=True,layout='constrained')
    for ax,(case,arm) in zip(axes.ravel(),((c,a) for c in CASES for a in ARMS)):
        group=[r for r in rows if r['case']==case and r['arm']==arm]
        for index,cell in enumerate(CELLS):
            row=next(r for r in group if r['cell']==cell);error=row['raw_position_error_km']
            if error is None:ax.text(index,0,'Missing',rotation=90);continue
            ax.bar(index,error,color=['.5','#176b8b','#b06624','#714d86'][index]);ax.text(index,error,f'{error:.3f}',ha='center',va='bottom',fontsize=9)
        ax.axhline(group[0]['operational_reference_error_km'],ls='--',color='#a34421',lw=1)
        ax.set_xticks(range(4),['00\nOld noise\nOld prior','10\nNew noise\nOld prior','01\nOld noise\nNew prior','11\nNew noise\nNew prior'],fontsize=8)
        ax.set_title(case+' · '+('c=0' if arm=='c0' else 'fitted c'));ax.set_ylabel('Raw position error (km)');ax.grid(axis='y',alpha=.2)
    ymax=max(r['raw_position_error_km'] or 0 for r in rows)
    for ax in axes.ravel():ax.set_ylim(0,max(.1,ymax*1.18))
    fig.suptitle('Original-CFO precision-block diagnostics\nDashed: unchanged VI operational reference;00/11 are reused conditional diagonals',fontsize=12)
    fig.savefig(out/'block_position_errors.png',dpi=170);plt.close(fig)
    write(out/'seal.json',dict(files={str(p):sha(p) for p in list(out.iterdir())+[Path(__file__),HERE/'RF_seal.json',ROOT/'audit/mechanism_terminal.json'] if p.is_file()}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('rf','geography'));parser.add_argument('--reference-latlon',nargs=2,type=float);a=parser.parse_args()
    if a.action=='rf':rf()
    elif a.reference_latlon is None:parser.error('released reference required')
    else:geography(a.reference_latlon)
