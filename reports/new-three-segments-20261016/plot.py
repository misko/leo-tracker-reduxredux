"""Scientific figures from saved conditional carrier fits; no position claims."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from search import ROOT,observations
from leo.contracts.regional_position import PositionOrbitBank,RegionalPrior
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import circular


def main():
    a=np.load(ROOT/'baseline.npz');b=np.load(ROOT/'orbit-bank.npz')
    ctx=json.loads((ROOT/'context.json').read_text());base=json.loads((ROOT/'baseline.json').read_text())
    search=json.loads((ROOT/'search-results.json').read_text());details=json.loads((ROOT/'details.json').read_text())
    bank=PositionOrbitBank(b['numbers'],b['nodes'],b['positions'],b['velocities'])
    prior=RegionalPrior(**ctx['prior']);v=np.array(ctx['vector'])
    fig,axes=plt.subplots(3,2,figsize=(14,11),layout='constrained')
    cdf,axcdf=plt.subplots(1,3,figsize=(15,4),layout='constrained')
    summaries=[]
    for j,(g,num) in enumerate(zip(base['groups'],[66854,58362,57864])):
        rows=a[g['name']+'_all_rows'];track=np.array(g['continuity_segments'][0]['rows'])
        obs=observations(a,ctx,rows);one=bank.select([list(bank.numbers).index(num)])
        saved=float(a['shifts'][list(bank.numbers).index(num)])
        s=next(s for s in search['groups'] if s['group']==g['name'] and s['selection']=='continuity_1')
        fit=s['arms']['fitted-c']['temporal']['all_timing_only']['ranked'][0]
        pred=predict_orbits(one,obs,prior,v[:2],np.array([fit['timing_s']]),derivatives=False)[0][:,0]
        old=predict_orbits(one,obs,prior,v[:2],np.array([saved]),derivatives=False)[0][:,0]
        shared=predict_orbits(one,obs,prior,v[:2],np.array([details['all_three_shared_timing_s']]),derivatives=False)[0][:,0]
        y=a['measured'][rows]-a['correction'][rows]
        active=np.isin(rows,track);associated=a['associated'][rows]
        # Lift only for display around the candidate; all scores use circular residuals.
        anchor=np.median(pred);yy=(pred-anchor)+circular(y-pred)
        ax=axes[j,0]
        ax.scatter(obs.times_s[~active],yy[~active]/1000,c='#999999',s=18,label='Other window points')
        ax.scatter(obs.times_s[active&~associated],yy[active&~associated]/1000,c='#555555',s=25,label='Track: unassociated')
        ax.scatter(obs.times_s[active&associated],yy[active&associated]/1000,c='#e69f00',s=35,label='Track: assigned elsewhere')
        ax.plot(obs.times_s,(pred-anchor)/1000,c='#009e73',lw=2,label=f'{num}, conditional timing fit')
        ax.plot(obs.times_s,(old-anchor)/1000,c='#0072b2',ls='--',label=f'{num}, saved timing'+(' (common fallback)' if num not in base['retained_candidates'] else ''))
        ax.set_title(f"RX1 CH{g['channel']} · {g['interval_s'][0]:.0f}–{g['interval_s'][1]:.0f} s")
        ax.set_ylabel('Calibrated carrier, relative (kHz)');ax.set_xlabel('Time from first sample (s)')
        ax.grid(alpha=.25);ax.legend(fontsize=8,loc='best')
        residual=circular(y-pred);rshared=circular(y-shared);rold=circular(y-old)
        ax=axes[j,1]
        ax.scatter(obs.times_s[active],residual[active],c='#009e73',s=22,label='Individual timing fit')
        ax.scatter(obs.times_s[active],rshared[active],facecolors='none',edgecolors='#cc79a7',s=42,label=f"Shared timing {details['all_three_shared_timing_s']:.2f} s")
        ax.axhline(0,c='black',lw=.7);ax.axhspan(-200,200,color='#009e73',alpha=.07)
        ax.set_ylim(-1200,1200);ax.set_xlabel('Time from first sample (s)');ax.set_ylabel('Carrier residual (Hz)')
        oldrms=float(np.sqrt(np.mean(rold[active]**2)));newrms=float(np.sqrt(np.mean(residual[active]**2)))
        ax.set_title(f"{len(track)} track points · {oldrms/1000:.1f} kHz → {newrms:.0f} Hz RMS")
        ax.grid(alpha=.25);ax.legend(fontsize=8)
        for label,r,color,style in [('Saved timing',rold,'#0072b2','--'),('Conditional timing',residual,'#009e73','-'),('Shared timing',rshared,'#cc79a7','-')]:
            xx=np.sort(np.abs(r[active]));axcdf[j].step(xx,np.arange(1,len(xx)+1)/len(xx),where='post',label=label,c=color,ls=style)
        axcdf[j].set_xscale('log');axcdf[j].set_xlim(10,100000);axcdf[j].set_ylim(0,1.02)
        axcdf[j].axvline(200,c='grey',lw=.8);axcdf[j].set_title(f"RX1 CH{g['channel']} · {num}")
        axcdf[j].set_xlabel('Absolute carrier residual (Hz)');axcdf[j].grid(alpha=.25);axcdf[j].legend(fontsize=8)
        summaries.append(dict(group=g['name'],satellite=num,saved_timing_s=saved,conditional_timing_s=fit['timing_s'],
            saved_candidate_rms_hz=oldrms,conditional_rms_hz=newrms,
            shared_timing_rms_hz=float(np.sqrt(np.mean(rshared[active]**2)))))
    fig.suptitle('New scan: coherent trajectories and conditional satellite explanations\nSaved position/calibration; no new frequency offsets; identities unverified',fontsize=14)
    fig.savefig(ROOT/'trajectories.png',dpi=150);plt.close(fig)
    axcdf[0].set_ylabel('Fraction of selected track points')
    cdf.suptitle('Carrier residual distributions — conditional fits, not position accuracy',fontsize=13)
    cdf.savefig(ROOT/'carrier-residual-cdf.png',dpi=150);plt.close(cdf)
    (ROOT/'figure-summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
    print(json.dumps(summaries,indent=2))


if __name__=='__main__':main()
