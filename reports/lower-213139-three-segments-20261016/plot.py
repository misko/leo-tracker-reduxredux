"""Trajectory, residual and association plots for the timing/q investigation."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from search import ROOT,observations
from leo.contracts.regional_position import PositionOrbitBank,RegionalPrior
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import circular,ALIAS_HZ


def main():
    a=np.load(ROOT/'baseline.npz');b=np.load(ROOT/'orbit-bank.npz');ctx=json.loads((ROOT/'context.json').read_text())
    base=json.loads((ROOT/'baseline.json').read_text());trial=json.loads((ROOT/'timing-trials.json').read_text())
    bank=PositionOrbitBank(b['numbers'],b['nodes'],b['positions'],b['velocities']);prior=RegionalPrior(**ctx['prior'])
    lookup={int(num):j for j,num in enumerate(bank.numbers)};v=np.array(ctx['vector'])
    fig,axes=plt.subplots(3,2,figsize=(14,11),layout='constrained')
    cdf,cs=plt.subplots(1,3,figsize=(15,4),layout='constrained');summary=[]
    for j,(g,p) in enumerate(zip(base['groups'],trial['profiles'])):
        rows=a[g['name']+'_all_rows'];track=np.array(p['rows']);obs=observations(a,ctx,rows);one=bank.select([lookup[p['satellite']]])
        saved=predict_orbits(one,obs,prior,v[:2],np.array([p['saved_timing_s']]),derivatives=False)[0][:,0]
        fitted=predict_orbits(one,obs,prior,v[:2],np.array([p['arms']['fitted-c']['all']['timing_s']]),derivatives=False)[0][:,0]
        y=a['measured'][rows]-a['correction'][rows];anchor=np.median(fitted);yy=fitted-anchor+circular(y-fitted)
        active=np.isin(rows,track);assoc=a['associated'][rows]
        ax=axes[j,0];ax.scatter(obs.times_s[~active],yy[~active]/1000,c='#aaaaaa',s=19,label='Other window points')
        ax.scatter(obs.times_s[active&~assoc],yy[active&~assoc]/1000,c='#555555',s=24,label='Track: originally unassociated')
        ax.scatter(obs.times_s[active&assoc],yy[active&assoc]/1000,c='#e69f00',s=33,label='Track: originally assigned elsewhere')
        ax.plot(obs.times_s,(saved-anchor)/1000,c='#0072b2',ls='--',label=f"{p['satellite']}: saved timing {p['saved_timing_s']:+.2f} s")
        ax.plot(obs.times_s,(fitted-anchor)/1000,c='#009e73',lw=2,label=f"{p['satellite']}: fitted timing {p['arms']['fitted-c']['all']['timing_s']:+.3f} s")
        ax.set_title(f"RX1 CH{g['channel']} · {g['interval_s'][0]:.0f}–{g['interval_s'][1]:.0f} s")
        ax.set_ylabel('Calibrated carrier, relative (kHz)');ax.set_xlabel('Time from first sample (s)');ax.grid(alpha=.25);ax.legend(fontsize=7.5)
        old=circular(y-saved);residual=circular(y-fitted)
        ax=axes[j,1];ax.scatter(obs.times_s[active],residual[active],c='#009e73',s=24)
        ax.axhline(0,c='black',lw=.7);ax.axhspan(-200,200,color='#009e73',alpha=.07);ax.set_ylim(-600,600)
        oldrms=float(np.sqrt(np.mean(old[active]**2)));newrms=float(np.sqrt(np.mean(residual[active]**2)))
        counts=[t['groups'][j]['intended_associated'] for t in [trial['trials'][0],trial['trials'][-2],trial['trials'][-1]]]
        ax.set_title(f"{len(track)} points · {oldrms/1000:.1f} kHz → {newrms:.0f} Hz RMS\nCandidate assignments: {counts[0]} → {counts[1]} → {counts[2]} (timing, then q)")
        ax.set_ylabel('Carrier residual (Hz)');ax.set_xlabel('Time from first sample (s)');ax.grid(alpha=.25)
        for label,r,color,ls in [('Saved timing',old,'#0072b2','--'),('Retimed; same after q refit',residual,'#009e73','-')]:
            xx=np.sort(abs(r[active]));cs[j].step(xx,np.arange(1,len(xx)+1)/len(xx),where='post',label=label,c=color,ls=ls)
        cs[j].set_xscale('log');cs[j].set_xlim(10,100000);cs[j].set_ylim(0,1.02);cs[j].axvline(200,c='grey',lw=.8)
        cs[j].set_title(f"RX1 CH{g['channel']} · {g['interval_s'][0]:.0f}–{g['interval_s'][1]:.0f} s · {p['satellite']}")
        cs[j].set_xlabel('Absolute carrier residual (Hz)');cs[j].grid(alpha=.25);cs[j].legend(fontsize=8)
        summary.append(dict(group=g['name'],satellite=p['satellite'],saved_candidate_rms_hz=oldrms,retimed_rms_hz=newrms))
    fig.suptitle('21:31 lower-edge scan: retained candidates with poor timing solutions\nSaved position and receiver calibration; no new frequency offsets; conditional identities',fontsize=14)
    fig.savefig(ROOT/'trajectories.png',dpi=150);plt.close(fig)
    cs[0].set_ylabel('Fraction of selected track points');cdf.suptitle('Carrier residual distributions — timing diagnostic, not position accuracy',fontsize=13)
    cdf.savefig(ROOT/'carrier-residual-cdf.png',dpi=150);plt.close(cdf)
    fig,ax=plt.subplots(figsize=(9,4),layout='constrained');x=np.arange(3);width=.25
    for k,(index,label,color) in enumerate([(0,'Original','#0072b2'),(-2,'Retimed','#009e73'),(-1,'Retimed + q refit','#e69f00')]):
        values=[t['intended_associated']/t['count'] for t in trial['trials'][index]['groups']]
        bars=ax.bar(x+(k-1)*width,values,width,label=label,color=color)
        for bar,t in zip(bars,trial['trials'][index]['groups']):
            ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+.02,f"{t['intended_associated']}/{t['count']}",ha='center',fontsize=9)
    ax.set_xticks(x,['CH4 0–40 s','CH4 175–210 s','CH5 175–200 s']);ax.set_ylim(0,1.15)
    ax.set_ylabel('Fraction assigned to proposed candidate');ax.set_title('Target-informed diagnostics; identity correctness is not independently verified')
    ax.legend(loc='upper left');fig.savefig(ROOT/'association-comparison.png',dpi=150);plt.close(fig)
    (ROOT/'figure-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
