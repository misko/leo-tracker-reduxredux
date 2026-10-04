"""Show actual owners and same-probe conflicts in the latest refined solver."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from solve_refined_scan_A import RefinedCalibration
from replay import NAMESPACE
from candidate_guided_refinement import circular

out=NAMESPACE/'full-scan-A-refinement/solver'
cal=RefinedCalibration();d=cal.d
final=json.loads((out/'A-fitted-c.json').read_text())['final']
owners={x['row_index']:x['catalog_number'] for x in final['assignments']}
own=np.array([owners.get(int(r),-1) for r in d.original_rows])
window=(d.receiver==1)&(d.channel==3)&(d.times>=100)&(d.times<=150)
selected={m['catalog_number']:m for m in final['selected']}
def prediction(n):
    p,v,_=cal.predict('fitted-c',np.array([int(np.flatnonzero(d.numbers==n)[0])]),selected[n]['offset_s'])
    return p[:,0],v[:,0]
p,v=prediction(66204);e=circular(d.measured-p)
assigned=window&(own==66204);alternatives=window&(own==-1)&v&(abs(e)<=600)
bygroup={int(d.group[i]):i for i in np.flatnonzero(own==66204)}
assert sum(assigned)==100 and sum(alternatives)==89
assert all(int(d.group[i]) in bygroup for i in np.flatnonzero(alternatives))
groups=set(d.group[alternatives]);choices=[g for g in groups if 110<=d.times[bygroup[int(g)]]<=125]
g=max(choices,key=lambda g:sum(alternatives&(d.group==g)))
j=bygroup[int(g)];example=[j]+np.flatnonzero(alternatives&(d.group==g)).tolist()
fig,axes=plt.subplots(3,1,figsize=(13,12),gridspec_kw={'height_ratios':[1.5,1.1,1]})
ax=axes[0];order=np.flatnonzero(window);order=order[np.argsort(d.times[order])]
for n in sorted(set(own[window]) - {-1,66204}):
    ix=window&(own==n);pp,_=prediction(n);yy=circular(pp[order])/1000
    yy[np.r_[False,abs(np.diff(yy))>100]]=np.nan
    ax.plot(d.times[order],yy,lw=.8,alpha=.55,label=f'Other orbit: {n}')
    ax.scatter(d.times[ix],circular(d.measured[ix])/1000,s=10,c='#bbbbbb',zorder=2)
un=window&(own==-1)
ax.scatter(d.times[un],circular(d.measured[un])/1000,s=22,c='#777777',label='Unassigned peaks',zorder=4)
ax.scatter(d.times[assigned],circular(d.measured[assigned])/1000,s=65,facecolors='none',edgecolors='#0072b2',lw=1.5,label='Assigned to 66204',zorder=5)
yy=circular(p[order])/1000;yy[np.r_[False,abs(np.diff(yy))>100]]=np.nan
ax.plot(d.times[order],yy,c='#d55e00',lw=2,label='66204 selected orbit + calibration',zorder=3)
ax.set(xlim=(100,150),ylim=(-114,114),ylabel='Wrapped CFO (kHz)',title='Full frequency view: the gray ridge overlaps points already assigned to 66204')
ax.legend(fontsize=8,ncol=3,loc='lower left')
ax=axes[1]
for i in np.flatnonzero(alternatives):
    jj=bygroup[int(d.group[i])];ax.plot([d.times[i],d.times[jj]],[e[i],e[jj]],c='#aaaaaa',lw=1,zorder=1)
ax.scatter(d.times[alternatives],e[alternatives],s=26,c='#777777',label='89 unassigned alternatives',zorder=3)
ax.scatter(d.times[assigned],e[assigned],s=65,facecolors='none',edgecolors='#0072b2',lw=1.5,label='100 assigned to 66204',zorder=4)
ax.axhline(0,c='#d55e00',lw=1.4);ax.set(xlim=(100,150),ylim=(-150,200),ylabel='GLRT − 66204 (Hz)',xlabel='Receive time (s)',title='Residual zoom: connectors join alternatives to the assigned peak in the SAME probe')
ax.legend(fontsize=9)
ax=axes[2];y=np.arange(len(example))
ax.scatter(e[example[1:]],y[1:],s=65,c='#777777')
ax.scatter([e[j]],[0],s=100,facecolors='none',edgecolors='#0072b2',lw=2)
ax.axvline(0,c='#d55e00',lw=1.4,label='66204 prediction')
labels=['Assigned to 66204']+[f'Unassigned alternative {i}' for i in range(1,len(example))]
for yi,ix in enumerate(example):ax.annotate(f'{e[ix]:+.1f} Hz · row {int(d.original_rows[ix])}',(e[ix],yi),xytext=(9,7),textcoords='offset points',fontsize=9)
ax.set(yticks=y,yticklabels=labels,xlim=(-150,200),ylim=(-.7,len(example)-.3),xlabel='GLRT − 66204 (Hz)',title=f'One actual probe at {d.times[j]:.6f} s: all these candidates share the same satellite/probe slot')
ax.invert_yaxis()
for ax in axes:ax.grid(alpha=.15)
fig.suptitle('Scan A · refined GLRT + greedy/replacement result\nNo other satellite is blocking these 89 alternatives: 66204 already owns a peak in every affected probe',fontsize=14)
fig.text(.5,.012,'Same saved fit and memberships; no reassignment. The last panel separates candidates into rows for readability, not different receive times.\nRule: one peak per satellite per probe. Multiple different satellites per probe ARE allowed.',ha='center',fontsize=10)
fig.tight_layout(rect=(0,.055,1,.94));fig.savefig(out/'66204-exclusivity-explained.png',dpi=160)
(out/'66204-exclusivity-example.json').write_text(json.dumps(dict(probe_group=int(g),time_s=float(d.times[j]),example=[dict(row=int(d.original_rows[i]),owner=int(own[i]),residual_hz=float(e[i]),time_s=float(d.times[i])) for i in example],matching_unassigned=89,all_blocked_by_same_satellite=True),indent=2))
print('Other owners in window',sorted(set(own[window])-{-1,66204}));print('Example',[(int(d.original_rows[i]),float(e[i]),int(own[i])) for i in example])
