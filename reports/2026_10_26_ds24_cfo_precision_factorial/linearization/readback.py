"""Saved-vector comparison only; no geometry, IQ, optimizer or GPS inputs."""
import time
STARTED=time.monotonic()
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
PREVIOUS=Path('/srv/bulk/leo/research/ds24-complete-owner-refinement-r01/response')


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def dump(p,x):
    with Path(p).open('x')as f:json.dump(x,f,indent=2,allow_nan=False);f.write('\n')


def main():
    if(HERE/'seal.json').exists():raise FileExistsError('one saved-only comparison')
    previous=PREVIOUS/'case_response.csv'
    contrasts=ROOT/'solver/rf_report/contrasts.json'
    oldseal=load(PREVIOUS/'seal.json');newseal=load(ROOT/'solver/rf_report/seal.json')
    assert sha(previous)==oldseal['files']['case_response.csv']
    assert sha(contrasts)==newseal['files'][str(contrasts)]
    oldrows=list(csv.DictReader(previous.open()));newrows=load(contrasts)
    expected={(case,arm)for case in ('DS24-0010','DS24-0011')for arm in ('c0','fitted_c')}
    assert len(oldrows)==len(newrows)==4
    old={(r['case'],r['arm']):r for r in oldrows};new={(r['case'],r['arm']):r for r in newrows}
    assert set(old)==set(new)==expected
    rows=[];vectors={}
    for case,arm in sorted(expected):
        a,b=old[case,arm],new[case,arm]
        assert b['complete']and b['packet_includes_noise_and_prior_precision']
        h=np.array([float(a['predicted_east_m']),float(a['predicted_north_m'])])
        vi=np.array([float(a['actual_RF_endpoint_east_m']),float(a['actual_RF_endpoint_north_m'])])
        isolated=np.array(b['vectors_km']['CFO_at_original_packet'])*1000
        full=np.array(b['vectors_km']['total'])*1000
        interaction=np.array(b['vectors_km']['interaction'])*1000
        assert all(v.shape==(2,)and np.isfinite(v).all()for v in (h,vi,isolated,full,interaction))
        # Independent saved scalar checks catch km/m and row-join mistakes.
        assert abs(np.linalg.norm(h)-float(a['predicted_norm_m']))<1e-9
        assert abs(np.linalg.norm(vi)-float(a['actual_RF_endpoint_norm_m']))<1e-9
        assert abs(np.linalg.norm(isolated)-b['norms_m']['CFO_at_original_packet'])<1e-9
        assert abs(np.linalg.norm(full)-b['norms_m']['total'])<1e-9
        assert abs(np.linalg.norm(vi-h)-float(a['linearization_difference_norm_m']))<1e-9
        vectors[case,arm]=dict(Hdelta=h,isolated_CFO=isolated,full_conditional=full,previous_VI=vi)
        row=dict(case=case,arm=arm)
        for label,v in vectors[case,arm].items():
            row.update({label+'_east_m':float(v[0]),label+'_north_m':float(v[1])})
        row.update(H_minus_isolated_east_m=float(h[0]-isolated[0]),H_minus_isolated_north_m=float(h[1]-isolated[1]),
            H_vs_isolated_difference_norm_m=float(np.linalg.norm(h-isolated)),H_vs_previous_VI_difference_norm_m=float(np.linalg.norm(h-vi)),
            full_conditional_vs_previous_VI_difference_norm_m=float(np.linalg.norm(full-vi)),
            factorial_interaction_east_m=float(interaction[0]),factorial_interaction_north_m=float(interaction[1]),
            factorial_interaction_norm_m=float(np.linalg.norm(interaction)))
        rows.append(row)
    with(HERE/'comparison.csv').open('x',newline='')as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    fig,axes=plt.subplots(2,2,figsize=(11,9),constrained_layout=True)
    styles=[('Hdelta','Saved local Hδ','#0072B2','o','-'),('isolated_CFO','CFO at original fixed packet','#D55E00','x','--'),
        ('full_conditional','Full conditional change','#009E73','s','-'),('previous_VI','Previous VI change','#CC79A7','+','--')]
    for ax,row in zip(axes.flat,rows):
        vv=vectors[row['case'],row['arm']]
        for key,label,color,marker,ls in styles:
            v=vv[key];ax.plot([0,v[0]],[0,v[1]],ls=ls,color=color,lw=1,alpha=.6)
            ax.scatter([v[0]],[v[1]],color=color,marker=marker,s=80,label=label,zorder=3)
        ax.axhline(0,color='.5',lw=.6);ax.axvline(0,color='.5',lw=.6);ax.grid(alpha=.2)
        ax.set(title=row['case']+' '+row['arm'].replace('fitted_c','fitted c'),xlabel='East displacement (m)',ylabel='North displacement (m)')
        ax.set_aspect('equal',adjustable='datalim');ax.margins(.16)
        ax.text(.03,.04,f"H vs fixed-packet CFO: {row['H_vs_isolated_difference_norm_m']:.3f} m",transform=ax.transAxes,fontsize=9)
    handles,labels=axes.flat[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='outside upper center',ncol=2,fontsize=9)
    fig.suptitle('The saved local response matches CFO-only movement at fixed precision\nPosthoc exposed-data mechanism comparison; no geographic accuracy claim',fontsize=12,y=.90)
    fig.savefig(HERE/'isolated_CFO_response.png',dpi=170);fig.savefig(HERE/'isolated_CFO_response.pdf');plt.close(fig)
    seconds=time.monotonic()-STARTED+1.
    if seconds>5:raise TimeoutError('five-second saved-only processing cap')
    paths=[Path(__file__),previous,PREVIOUS/'seal.json',contrasts,ROOT/'solver/rf_report/seal.json',ROOT/'solver/RF_seal.json']
    dump(HERE/'summary.json',dict(rows=rows,matching_case_arm_set_exact=True,km_to_m_norm_checks_pass=True,
        cumulative_numeric_seconds=seconds,initial_metadata_allowance_seconds=1.,saved_only=True,GPS_or_geometry_or_fits=False,
        source_bindings={str(p):sha(p)for p in paths}))
    dump(HERE/'seal.json',dict(source_bindings={str(p):sha(p)for p in paths},
        files={p.name:sha(p)for p in HERE.iterdir()if p.is_file()and p.name!='seal.json'}))
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
