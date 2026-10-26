"""Frozen saved-output contrasts and separately released geographic evaluation."""
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
OLD=Path('/srv/bulk/leo/research/ds24-complete-owner-refinement-r01/position')
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
    if any(v.shape!=(2,) or not np.isfinite(v).all() for v in x.values()):raise ValueError('finite 2D endpoints required')
    a=x['10']-x['00'];b=x['11']-x['01'];c=x['01']-x['00'];d=x['11']-x['10']
    values=dict(CFO_at_original_packet=a,CFO_at_refined_packet=b,packet_at_original_CFO=c,packet_at_refined_CFO=d,
        interaction=x['11']-x['10']-x['01']+x['00'],symmetric_CFO=(a+b)/2,symmetric_packet=(c+d)/2,total=x['11']-x['00'])
    if not np.allclose(values['symmetric_CFO']+values['symmetric_packet'],values['total'],atol=1e-12,rtol=0):raise ValueError('signed vector decomposition does not close')
    return dict(complete=True,vectors_km={k:v.tolist() for k,v in values.items()},
        norms_m={k:float(np.linalg.norm(v)*1000) for k,v in values.items()},
        vector_closure_error_km=float(np.linalg.norm(values['symmetric_CFO']+values['symmetric_packet']-values['total'])),
        displacement_norms_are_not_additive=True,packet_includes_noise_and_prior_precision=True)


def rf():
    verify(HERE/'RF_seal.json');out=HERE/'rf_report';out.mkdir(exist_ok=False);rows=[];comparisons=[]
    execution=read(HERE/'execution.json')
    for slot in execution['all16_slots']:
        row=dict(slot)
        if row['status']=='complete':
            x=row.pop('endpoint_east_north_km');row.update(east_km=x[0],north_km=x[1])
        rows.append(row)
    for case in CASES:
        for arm in ARMS:
            rr={r['cell']:r for r in rows if r['case']==case and r['arm']==arm}
            points={c:[rr[c]['east_km'],rr[c]['north_km']] if rr[c]['status']=='complete' else None for c in CELLS}
            comparisons.append(dict(case=case,arm=arm,**contrasts(points)))
    csv_write(out/'outcomes.csv',rows);write(out/'contrasts.json',comparisons)
    write(out/'summary.json',dict(rows=rows,contrasts=comparisons,slots=16,completed=sum(x['status']=='complete' for x in rows),
        cumulative_worker_seconds=execution['cumulative_worker_seconds'],objective_kind='conditional_Gaussian_not_VI_ELBO',GPS_used=False))
    fig,axes=plt.subplots(2,2,figsize=(10.7,8),layout='constrained')
    for ax,q in zip(axes.ravel(),comparisons):
        if not q['complete']:ax.text(.5,.5,'Incomplete factorial',ha='center');continue
        rr={r['cell']:r for r in rows if r['case']==q['case'] and r['arm']==q['arm']};origin=np.array([rr['00']['east_km'],rr['00']['north_km']])
        for cell in CELLS:
            point=(np.array([rr[cell]['east_km'],rr[cell]['north_km']])-origin)*1000
            ax.scatter(*point,s=35);ax.annotate(cell,point,xytext=(5,5),textcoords='offset points')
        a=np.asarray(q['vectors_km']['symmetric_CFO'])*1000;b=np.asarray(q['vectors_km']['symmetric_packet'])*1000
        ax.annotate('',a,xytext=[0,0],arrowprops=dict(arrowstyle='->',color='#176b8b',lw=2))
        ax.annotate('',a+b,xytext=a,arrowprops=dict(arrowstyle='->',color='#b06624',lw=2))
        ax.plot([0,(a+b)[0]],[0,(a+b)[1]],'--',color='.4',lw=1)
        ax.set_title(q['case']+' · '+('c=0' if q['arm']=='c0' else 'fitted c'))
        ax.set_xlabel('East displacement from cell00 (m)');ax.set_ylabel('North displacement from cell00 (m)');ax.grid(alpha=.2);ax.margins(.22)
    fig.suptitle('Actual nonlinear factorial: signed vectors, not additive displacement norms\nBlue: symmetric CFO effect; orange: full precision-packet effect',fontsize=12)
    fig.savefig(out/'factorial_vectors.png',dpi=170);plt.close(fig)
    files=[p for p in out.iterdir() if p.is_file()]+[Path(__file__),HERE/'RF_seal.json']
    write(out/'seal.json',dict(files={str(p):sha(p) for p in files}));print(json.dumps(comparisons,indent=2))


def latlon(x):return 37.906+x[1]/111.,-122.545+x[0]/(111.32*math.cos(math.radians(37.906)))


def distance(a,b):
    la,lo,lb,lp=map(math.radians,(*a,*b));h=math.sin((lb-la)/2)**2+math.cos(la)*math.cos(lb)*math.sin((lp-lo)/2)**2
    return 6371.0088*2*math.asin(math.sqrt(min(1.,max(0.,h))))


def geography(reference):
    verify(HERE/'RF_seal.json');verify(HERE/'rf_report/seal.json')
    protocol=read(HERE/'protocol.json')
    if protocol['files'][str(Path(__file__))]!=sha(__file__):raise ValueError('evaluator source changed after prefit freeze')
    audit=read(ROOT/'audit/terminal.json')
    if not audit['all_passed'] or not audit.get('RF_ready_for_separate_geographic_evaluation') or audit['RF_seal_sha256']!=sha(HERE/'RF_seal.json'):raise ValueError('exact passing terminal audit required')
    out=HERE/'geographic';out.mkdir(exist_ok=False);rows=[]
    for row in read(HERE/'rf_report/summary.json')['rows']:
        original=read(OLD/row['case']/'original'/row['arm']/'raw_endpoint.json')['summary']['endpoint_east_north_km']
        baseline=distance(latlon(original),reference)
        error=distance(latlon([row['east_km'],row['north_km']]),reference) if row['status']=='complete' else None
        rows.append(dict(row,raw_position_error_km=error,operational_reference_error_km=baseline,
            raw_gain_vs_operational_m=1000*(baseline-error) if error is not None else None,
            operational_policy_error_km=baseline,operational_policy='exact_original_reference'))
    csv_write(out/'outcomes.csv',rows);write(out/'summary.json',dict(rows=rows,reference_latlon=reference,slots=16,new_fits=0,
        root_release='explicit coordinator message after passing RF audit',operational_policy='original_reference'))
    fig,axes=plt.subplots(2,2,figsize=(10.7,8),sharey=True,layout='constrained')
    for ax,(case,arm) in zip(axes.ravel(),((c,a) for c in CASES for a in ARMS)):
        group=[r for r in rows if r['case']==case and r['arm']==arm]
        for index,cell in enumerate(CELLS):
            row=next(r for r in group if r['cell']==cell);error=row['raw_position_error_km']
            if error is None:ax.text(index,0,'Missing',rotation=90);continue
            ax.bar(index,error,color=['.5','#176b8b','#b06624','#714d86'][index]);ax.text(index,error,f'{error:.3f}',ha='center',va='bottom',fontsize=9)
        ax.axhline(group[0]['operational_reference_error_km'],ls='--',color='#a34421',lw=1)
        ax.set_xticks(range(4),['00\nOld CFO\nOld packet','10\nRefined CFO\nOld packet','01\nOld CFO\nRefined packet','11\nRefined CFO\nRefined packet'],fontsize=8)
        ax.set_title(case+' · '+('c=0' if arm=='c0' else 'fitted c'));ax.set_ylabel('Raw position error (km)');ax.grid(axis='y',alpha=.2)
    ymax=max(r['raw_position_error_km'] or 0 for r in rows)
    for ax in axes.ravel():ax.set_ylim(0,max(.1,ymax*1.18))
    fig.suptitle('Frozen-precision conditional-Gaussian factorial\nDashed: unchanged original VI operational reference; diagnostics do not adopt a cell',fontsize=12)
    fig.savefig(out/'factorial_position_errors.png',dpi=170);plt.close(fig)
    files=[p for p in out.iterdir() if p.is_file()]+[Path(__file__),HERE/'RF_seal.json',ROOT/'audit/terminal.json']
    write(out/'seal.json',dict(files={str(p):sha(p) for p in files}));print(json.dumps(rows,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('rf','geography'));parser.add_argument('--reference-latlon',nargs=2,type=float);a=parser.parse_args()
    if a.action=='rf':rf()
    elif a.reference_latlon is None:parser.error('released reference required')
    else:geography(a.reference_latlon)
