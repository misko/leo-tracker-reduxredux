"""Retrospective decision-layer audit; saved numerical fits are not rerun."""
import csv
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from policy import select, POLICY

OUT=Path(__file__).resolve().parent
SEALED=OUT.parent/'2026_11_01_reconsideration_population'
sys.path.insert(0,str(OUT/'validation'))
from predictive_uniqueness import from_additional_checks


def read(p):return json.loads(Path(p).read_text())
def write(p,z):p.write_text(json.dumps(z,indent=2,allow_nan=False)+'\n')
def table(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)


def main():
    outcomes=[];ledger=[];sources={}
    for path in sorted((SEALED/'receipts').glob('*.json')):
        result=read(path);case=result['case'];guards={}
        for record in result['records']['combined']:
            if not record.get('accepted'):continue
            extra=OUT/'validation'/case/'additional_checks.json'
            checks=read(extra)
            assert checks['old']==record['target']
            assert checks['new']==record['hypothesis']['norad']
            assert all(not r['destination_already_baseline_owned'] and not r['unexpected_owners'] and not r['lost_curved_ids'] for r in checks['ownership'].values())
            guards[record['name']]=from_additional_checks(checks)
            sources[str(extra)]=hashlib.sha256(extra.read_bytes()).hexdigest()
        chosen=select(result['baseline'],result['records']['combined'],guards)
        ledger.append(dict(case=case,execution_status=result.get('execution_status','complete'),**chosen,guards=guards))
        sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        for method in ('ALGO06','combined','guarded_candidate'):
            values=chosen if method=='guarded_candidate' else result['methods'][method]
            for arm,r in values['final'].items():
                b=result['baseline'][arm]
                assert r['associated']==b['associated']
                if values['selected'] is None:assert r==b
                outcomes.append(dict(case=case,dataset=case[:4],method=method,arm=arm,error_m=r['error_m'],
                    baseline_m=b['error_m'],delta_m=r['error_m']-b['error_m'],associated=r['associated'],
                    objective=r['objective'],baseline_objective=b['objective'],selected=values['selected']))
    table(OUT/'population_positions.csv',outcomes)
    summary=[]
    for ds in ('DS26','DS27','DS28'):
        for a in ('c0','fitted_c'):
            for method in ('ALGO06','combined','guarded_candidate'):
                rows=[r for r in outcomes if r['dataset']==ds and r['arm']==a and r['method']==method]
                err=np.array([r['error_m'] for r in rows]);delta=np.array([r['delta_m'] for r in rows])
                summary.append(dict(dataset=ds,arm=a,method=method,n=len(rows),mean_m=float(err.mean()),median_m=float(np.median(err)),
                    p90_m=float(np.quantile(err,.9)),p95_m=float(np.quantile(err,.95)),max_m=float(err.max()),
                    improved25=int((delta< -25).sum()),regressed25=int((delta>25).sum()),within500=int((err<500).sum())))
    table(OUT/'population_summary.csv',summary)
    write(OUT/'population_audit.json',dict(policy=POLICY,scope='Retrospective guard on frozen complete-cohort outputs; no new numerical reruns or independent validation',
        source_sha256=sources,outcomes=ledger,summary=summary))
    fig,axes=plt.subplots(2,3,figsize=(13,7),layout='constrained')
    for j,ds in enumerate(('DS26','DS27','DS28')):
        for i,a in enumerate(('c0','fitted_c')):
            ax=axes[i,j]
            for method,color,style in [('ALGO06','#333333','-'),('combined','#dc8a23','--'),('guarded_candidate','#276bb0','-.')]:
                v=sorted(r['error_m']/1000 for r in outcomes if r['dataset']==ds and r['arm']==a and r['method']==method)
                ax.step(v,np.arange(1,len(v)+1)/len(v),where='post',color=color,linestyle=style,label=method)
            ax.set(title=f'{ds}: {a}',xlabel='Position error (km)',ylabel='Fraction of available outcomes');ax.grid(alpha=.2)
    axes[0,0].legend(fontsize=8)
    fig.suptitle('Retrospective guard audit: existing fits, stricter identity selection; causal TLEs only')
    fig.savefig(OUT/'population_cdf.png',dpi=170);plt.close(fig)
    print('Audited',len(ledger),'outcomes; guarded changes:',[(r['case'],r['selected']) for r in ledger if r['selected']])


if __name__=='__main__':main()
