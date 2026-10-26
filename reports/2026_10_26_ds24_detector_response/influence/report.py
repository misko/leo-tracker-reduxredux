"""Report saved selection and raw metadata only; no new sensitivity scores."""
import csv
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent;OUT=HERE/'report'
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')
def load(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n')
def write(p,rows):
    with Path(p).open('w',newline='')as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def main():
    if OUT.exists():raise FileExistsError('preserve original reporting')
    for p,h in load(HERE/'RF_seal.json')['files'].items():assert sha(p)==h,p
    OUT.mkdir();results=load(HERE/'results.json');requests=load(HERE/'window_requests.json');selected=[];points=[]
    for s in results['selection']:
        obs={o['observation_id']:o for o in load(SOURCE/s['case']/'observations.json')}
        for role in ('target','control'):
            o=s[role]
            if o is None:continue
            modes=next(c for c in results['checks']if c['case']==s['case']and c['arm']=='c0')['physical_modes_in_original_parent']
            row=dict(case=s['case'],role=role,owner=o['owner'],family=o['family'],receiver=o['receiver'],channel=o['channel'],points=o['points'],
                span_s=o['end_s']-o['start_s'],original_three_physical_mode_slots=str(o['family'])in modes,
                c0_one_Hz_proxy_m=o['arms']['c0']['one_Hz_proxy_m'],fitted_one_Hz_proxy_m=o['arms']['fitted_c']['one_Hz_proxy_m'],
                c0_twenty_Hz_proxy_m=o['arms']['c0']['twenty_Hz_proxy_m'],fitted_twenty_Hz_proxy_m=o['arms']['fitted_c']['twenty_Hz_proxy_m'])
            selected.append(row)
            for oid in o['observation_ids']:
                p=obs[oid];points.append(dict(case=s['case'],role=role,owner=o['owner'],native_id=oid,time_s=p['time_s'],native_CFO_Hz=p['measured_cfo_hz'],
                    margin=p['fractional_margin'],receiver=p['receiver'],channel=p['channel'],actual_rf_hz=p['actual_rf_hz'],selected_for_request=any(r['native_observation_id']==oid for r in requests)))
    write(OUT/'selected_owners.csv',selected);write(OUT/'complete_selected_owner_points.csv',points)
    fig,axes=plt.subplots(1,2,figsize=(12,5),constrained_layout=True)
    for ax,case in zip(axes,('DS24-0010','DS24-0011')):
        pool=[o for o in results['owners']if o['case']==case and o['eligible']]
        ax.scatter([o['points']for o in pool],[min(o['arms'][a]['twenty_Hz_proxy_m']for a in ('c0','fitted_c'))for o in pool],color='.65',s=24,label='All eligible complete owners')
        for role,color in [('target','#D55E00'),('control','#0072B2')]:
            r=next(o for o in selected if o['case']==case and o['role']==role)
            y=min(r['c0_twenty_Hz_proxy_m'],r['fitted_twenty_Hz_proxy_m']);ax.scatter([r['points']],[y],color=color,s=70,label=role.capitalize())
            ax.annotate(f"RX{r['receiver']} CH{r['channel']} / {r['family']}",(r['points'],y),xytext=(5,7),textcoords='offset points',fontsize=8)
        ax.set(title=case,xlabel='Complete original curved-owner points',ylabel='20 Hz RMS quadratic-bias susceptibility (m)\nSmaller of the two original c-arm weak-axis responses')
        ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('RF-only accepted-owner panel: susceptibility is not observed bias\nOriginal shared nuisance assumptions retained; no position fit or GPS selection',fontsize=12)
    fig.savefig(OUT/'selected_susceptibility.png',dpi=170);fig.savefig(OUT/'selected_susceptibility.pdf');plt.close(fig)

    fig,axes=plt.subplots(2,2,figsize=(12,7),constrained_layout=True)
    for ax,r in zip(axes.flat,selected):
        rows=sorted([p for p in points if p['owner']==r['owner']],key=lambda p:(p['time_s'],p['native_id']))
        ax.scatter([p['time_s']for p in rows],[p['native_CFO_Hz']/1000 for p in rows],s=14,color='.4',label='All original native winners')
        picks=[p for p in rows if p['selected_for_request']]
        ax.scatter([p['time_s']for p in picks],[p['native_CFO_Hz']/1000 for p in picks],marker='*',s=130,color='#D55E00',label='Fixed 25% / 75% time-order requests')
        ax.set(title=f"{r['case']} {r['role']}: RX{r['receiver']} CH{r['channel']}, {r['points']} points",xlabel='Original scan midpoint time (s)',ylabel='Original raw fractional CFO (kHz)')
        ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('All 159 selected-owner observations are retained\nOnly eight time-quantile windows are requested; no IQ or detector execution',fontsize=12)
    fig.savefig(OUT/'requested_windows.png',dpi=170);fig.savefig(OUT/'requested_windows.pdf');plt.close(fig)
    dump(OUT/'seal.json',dict(source_sha256=sha(Path(__file__)),RF_seal_sha256=sha(HERE/'RF_seal.json'),saved_outputs_only=True,
        files={str(p.relative_to(HERE)):sha(p)for p in sorted(OUT.iterdir())if p.is_file()}))
    print('REPORT_READY',len(selected),len(points),len(requests))


if __name__=='__main__':main()
