"""Geography released only after immutable RF inference; no fit selection."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'report'
NAMES=('full','overlap','plus_A','plus_B','plus_AB','minus_dominant','full_minus_dominant')
LABELS=('All curved','Shared coverage','+ 65089','+ 68102','+ Both','Shared − 67123','All − 67123')

def load(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def error(point,reference):
    lat=37.906+point[1]/111;lon=-122.545+point[0]/(111.32*math.cos(math.radians(37.906)))
    a,b,c,d=map(math.radians,(lat,lon,*reference))
    v=math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 6371.0088*2*math.asin(math.sqrt(min(1,max(0,v))))
def write(p,v):
    with Path(p).open('x') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n')
def figure(fig,name):
    for ext in ('png','pdf'):fig.savefig(OUT/(name+'.'+ext),dpi=170)
    plt.close(fig)

def main(reference):
    for mapping in (load(ROOT/'RF_seal.json')['files'],load(ROOT/'protocol.json')['sources']):
        for p,h in mapping.items():assert sha(p)==h,p
    v=load(ROOT/'execution.json');assert len(v['fits'])==14 and len(v['scores'])==10
    assert all(r['status']=='complete' for r in v['fits']+v['scores'])
    OUT.mkdir(exist_ok=True)
    rows=[]
    for r in v['fits']:
        scores=next((s for s in v['scores'] if s['method']==r['method'] and s['arm']==r['arm']),None)
        rows.append(dict(method=r['method'],arm=r['arm'],points=r['points'],
            error_km=error(r['endpoint_east_north_km'],reference),frequency_RMS_hz=r['frequency_RMS_hz'],
            phase_checks_pass=r['phase_checks_pass'],training_checks_pass=r['training_checks_pass'],
            any_iteration_budget=any(h['fit']['stopped']=='iteration_budget' for h in r['history']),
            conditional_weak_axis_sigma_km=r['information']['conditional_axis_sigma_km'][0],
            held_movement_gain=None if scores is None else scores['movement_gain']))
    write(OUT/'summary.json',dict(rows=rows,reference_latlon=reference,GPS_evaluation_only=True,
        selection_from_prior_development_error=True,no_new_algorithm=True,
        all_fixed_position_checks_pass=all(e['checks']['checks_pass'] for s in v['scores'] for e in s['endpoints'].values())))
    with (OUT/'results.csv').open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    selection=load(ROOT/'protocol.json')['selection'];table=sorted(selection['table'],key=lambda r:-r['full'])
    fig,ax=plt.subplots(figsize=(13,4.6),layout='constrained');xx=np.arange(len(table))
    ax.bar(xx-.18,[100*r['full']/2885 for r in table],.36,label='All curved: 2,885 points / 21 families')
    ax.bar(xx+.18,[100*r['overlap']/1034 for r in table],.36,label='Shared coverage: 1,034 points / 7 families')
    ax.set_xticks(xx,[str(r['norad']) for r in table],rotation=60);ax.set_ylabel('Fraction of retained points (%)')
    ax.set_xlabel('Satellite family');ax.legend();ax.grid(axis='y',alpha=.2)
    ax.set_title('DS24-0012: matching coverage removes unique families and concentrates evidence')
    figure(fig,'family_composition')
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for i,arm in enumerate(('c0','fitted_c')):
        rr=[next(r for r in rows if r['method']==m and r['arm']==arm) for m in NAMES]
        axes[0].bar(np.arange(7)+(i-.5)*.36,[r['error_km'] for r in rr],.34,label=arm,
                    hatch=['///' if not r['training_checks_pass'] else '' for r in rr])
        ss=[next(s for s in v['scores'] if s['method']==m and s['arm']==arm) for m in NAMES[2:6]]
        axes[1].bar(np.arange(4)+(i-.5)*.36,[s['movement_gain'] for s in ss],.34,label=arm)
    axes[0].set_xticks(np.arange(7),LABELS,rotation=40,ha='right');axes[0].set_ylabel('Position error (km)')
    axes[0].set_title('Every endpoint; hatching = an earlier refresh hit its iteration cap')
    axes[1].set_xticks(np.arange(4),LABELS[2:6],rotation=30,ha='right')
    axes[1].set_ylabel('Held predictive loss reduction (positive supports movement)')
    axes[1].set_title('Same predictor at own versus shared-coverage endpoint\n1,346 identical held points; training has full-data precision exposure')
    for ax in axes:ax.legend();ax.grid(axis='y',alpha=.2);ax.axhline(0,color='.2',lw=.7)
    figure(fig,'position_and_prediction')
    fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    colors=dict(zip(NAMES,plt.get_cmap('tab10').colors[:7]))
    truth=np.array([(reference[1]+122.545)*111.32*math.cos(math.radians(37.906)),(reference[0]-37.906)*111])
    for ax,arm in zip(axes,('c0','fitted_c')):
        for name,label in zip(NAMES,LABELS):
            r=next(r for r in v['fits'] if r['method']==name and r['arm']==arm);xy=np.array(r['endpoint_east_north_km'])
            ax.scatter(*xy,color=colors[name],label=label,marker='x' if not r['training_checks_pass'] else 'o')
            if name in ('full','overlap','plus_AB'):
                fisher=np.array(r['information']['mean_information_per_km2']);eig,vec=np.linalg.eigh(fisher)
                theta=np.linspace(0,2*np.pi,200);ellipse=vec@((1/np.sqrt(eig))[:,None]*np.array([np.cos(theta),np.sin(theta)]))
                ax.plot(xy[0]+ellipse[0],xy[1]+ellipse[1],color=colors[name],alpha=.6)
        ax.scatter(*truth,marker='*',s=160,c='black',label='Evaluation site')
        ax.set_aspect('equal',adjustable='datalim');ax.grid(alpha=.2);ax.set_xlabel('East from regional center (km)');ax.set_ylabel('North (km)');ax.set_title(arm)
    axes[1].legend(fontsize=7,loc='center left',bbox_to_anchor=(1,0.5))
    fig.suptitle('Local 1σ mean-information ellipses: conditional on frozen identity, phase and precision\nNot calibrated geographic confidence regions; no inference uses the evaluation site')
    figure(fig,'endpoints_and_information')
    write(OUT/'seal.json',dict(files={str(p):sha(p) for p in OUT.iterdir() if p.is_file()},source_sha256=sha(__file__)))
    print(json.dumps(rows,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--reference-latlon',required=True,nargs=2,type=float)
    main(parser.parse_args().reference_latlon)
