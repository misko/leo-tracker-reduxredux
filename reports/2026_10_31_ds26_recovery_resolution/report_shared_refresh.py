"""Reporting only: compare sealed posterior projections, including failures."""
from pathlib import Path
import csv
import hashlib
import json
import math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).parent/'shared-refresh'

def distance_m(latlon):
    a,b,c,d=map(math.radians, (37.849061591561885,-122.48574968092912,*latlon))
    h=math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 6371008.8*2*math.asin(min(1,math.sqrt(h)))

def run():
    rows=[]
    for folder in sorted(ROOT.glob('DS26-*')):
        assert json.loads((folder/'terminal.json').read_text())['completed']
        seal=json.loads((folder/'inference_seal.json').read_text())
        assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in seal['artifacts_sha256'].items())
        rows.extend(json.loads((folder/'summary.json').read_text())['rows'])
    records=[]
    for r in rows:
        records.append({k:r[k] for k in ['case','variant','role','arm','paired_valid','exact_verified','added_points','lost_points','final_phase_change_s']}|
                       dict(target_RMS_hz=r['target_diagnostics'][0]['RMS_hz'] if r['target_diagnostics'] else None,
                            failed_gates=len(r['failed_slacks']),position_error_m=distance_m(r['endpoint_latlon'])))
    with (ROOT/'paired-table.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]),lineterminator='\n');w.writeheader();w.writerows(records)
    (ROOT/'reporting-summary.json').write_text(json.dumps(dict(rows=records,GPS_used_only_after_inference_seal=True,newly_qualified_points=0),indent=2)+'\n')
    fig,axes=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for i,case in enumerate(['DS26-0265','DS26-0223']):
        for j,arm in enumerate(['c0','fitted_c']):
            ax=axes[i,j]
            for variant,color,label in [('unchanged','#2166ac','Original marginal model'),('shared_posterior','#df8700','Shared satellite posterior means')]:
                r=next(r for r in rows if r['case']==case and r['arm']==arm and r['variant']==variant and r['role']=='target_0')
                t=r['target_diagnostics'][0]
                ax.plot(t['times_s'],t['residual_hz'],'.-',ms=2,lw=.7,color=color,label=f"{label}: {t['RMS_hz']:.1f} Hz")
            ax.axhline(0,color='.5',lw=.6);ax.grid(alpha=.2);ax.set_title(f'{case} / {arm} — both additions rejected')
            ax.set_xlabel('Scan time (s)');ax.set_ylabel('Target residual (Hz)');ax.legend(fontsize=8)
    fig.suptitle('Existing shared satellite phase/orbit updates do not resolve these curves\nSame causal priors and receiver means; all points retained; incumbent gates also fail after projection')
    fig.savefig(ROOT/'shared-refresh.png',dpi=150);fig.savefig(ROOT/'shared-refresh.pdf');plt.close(fig)
    print(json.dumps(records,indent=2))

if __name__=='__main__':run()
