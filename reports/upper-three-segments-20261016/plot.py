"""Carrier fits and residual distributions with their conditional scope explicit."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from search import ROOT,observations
from leo.contracts.regional_position import PositionOrbitBank,RegionalPrior
from leo.analysis.regional_position_score import circular
from leo.analysis.hard60_score import predict_orbits


def main():
    a=np.load(ROOT/'baseline.npz');b=np.load(ROOT/'orbit-bank.npz');ctx=json.loads((ROOT/'context.json').read_text())
    base=json.loads((ROOT/'baseline.json').read_text());shape=json.loads((ROOT/'shape-controls.json').read_text())
    geometry=json.loads((ROOT/'geometry-control.json').read_text());geo=geometry['folds'][0]['selected']
    bank=PositionOrbitBank(b['numbers'],b['nodes'],b['positions'],b['velocities']);prior=RegionalPrior(**ctx['prior'])
    v=np.array(ctx['vector']);lookup={int(n):j for j,n in enumerate(bank.numbers)}
    # Convert the fitted shared site's reported coordinates back using its saved
    # displacement parameters; obtained from the same local coordinate map.
    from scipy.optimize import least_squares
    from leo.analysis.regional_position_score import coordinates
    point=least_squares(lambda x:np.array(coordinates(prior,x))-
        [geo['latitude_deg'],geo['longitude_deg']],v[:2],xtol=1e-12,gtol=1e-12,ftol=1e-12).x
    fig,axes=plt.subplots(3,2,figsize=(14,11),layout='constrained')
    cdf,cs=plt.subplots(1,3,figsize=(15,4),layout='constrained')
    summaries=[]
    for j,(g,gg,original) in enumerate(zip([g for g in shape['groups'] if g['part']==0],geo['groups'],base['groups'])):
        rows=a[g['group']+'_all_rows'];track=np.array(g['rows']);obs=observations(a,ctx,rows)
        f=g['arms']['published']['all'][0];one=bank.select([lookup[f['satellite']]])
        pred=predict_orbits(one,obs,prior,v[:2],np.array([f['timing_s']]),derivatives=False)[0][:,0]+f['offset_hz']
        other=bank.select([lookup[gg['satellite']]])
        pg=predict_orbits(other,obs,prior,point,np.array([gg['timing_s']]),derivatives=False)[0][:,0]+gg['offset_hz']
        saved=predict_orbits(one,obs,prior,v[:2],np.array([a['shifts'][lookup[f['satellite']]]]),derivatives=False)[0][:,0]
        y=a['measured'][rows]-a['correction'][rows];active=np.isin(rows,track);assoc=a['associated'][rows]
        anchor=np.median(pred);lift=(pred-anchor)+circular(y-pred)
        ax=axes[j,0];ax.scatter(obs.times_s[~active],lift[~active]/1000,c='#bbbbbb',s=20,label='Other window points')
        ax.scatter(obs.times_s[active&~assoc],lift[active&~assoc]/1000,c='#555555',s=24,label='Track: unassociated')
        ax.scatter(obs.times_s[active&assoc],lift[active&assoc]/1000,c='#e69f00',s=30,label='Track: assigned')
        ax.plot(obs.times_s,(pred-anchor)/1000,c='#009e73',lw=2,label=f"Saved site: {f['satellite']}, timing + offset fit")
        ax.plot(obs.times_s,(pred-anchor+circular(pg-pred))/1000,c='#cc79a7',ls='--',label=f"Changed site: {gg['satellite']}, timing + offset fit")
        ax.set_title(f"RX{g['receiver']} CH{g['channel']} · {original['interval_s'][0]:.0f}–{original['interval_s'][1]:.0f} s")
        ax.set_xlabel('Time from first sample (s)');ax.set_ylabel('Calibrated carrier, relative (kHz)')
        ax.grid(alpha=.25);ax.legend(fontsize=7.5)
        r=circular(y-pred);rg=circular(y-pg);rs=circular(y-saved)
        ax=axes[j,1];ax.scatter(obs.times_s[active],r[active],c='#009e73',s=23,label='Saved site, conditional fit')
        ax.scatter(obs.times_s[active],rg[active],facecolors='none',edgecolors='#cc79a7',s=38,label='Changed site, conditional fit')
        ax.axhspan(-200,200,color='#009e73',alpha=.07);ax.axhline(0,c='black',lw=.7)
        ax.set_title(f"{len(track)} continuity points · {np.sqrt(np.mean(r[active]**2)):.0f} → {np.sqrt(np.mean(rg[active]**2)):.0f} Hz in-sample RMS")
        ax.set_ylim(-2000,2000);ax.set_xlabel('Time from first sample (s)');ax.set_ylabel('Carrier residual (Hz)')
        ax.legend(fontsize=8);ax.grid(alpha=.25)
        for label,res,color,ls in [('Saved candidate parameters',rs,'#0072b2','--'),('Saved site, fitted timing/offset',r,'#009e73','-'),('Changed site, fitted timing/offset',rg,'#cc79a7','-')]:
            xx=np.sort(abs(res[active]));cs[j].step(xx,np.arange(1,len(xx)+1)/len(xx),where='post',label=label,c=color,ls=ls)
        cs[j].set_xscale('log');cs[j].set_xlim(10,100000);cs[j].set_ylim(0,1.02);cs[j].axvline(200,c='grey',lw=.8)
        cs[j].set_xlabel('Absolute carrier residual (Hz)');cs[j].set_title(f"RX{g['receiver']} CH{g['channel']}")
        cs[j].grid(alpha=.25);cs[j].legend(fontsize=7)
        summaries.append(dict(group=g['group'],count=len(track),saved_site_satellite=f['satellite'],
            saved_site_rms_hz=float(np.sqrt(np.mean(r[active]**2))),changed_site_satellite=gg['satellite'],
            changed_site_rms_hz=float(np.sqrt(np.mean(rg[active]**2)))))
    fig.suptitle('Upper-edge scan: coherent trajectories and ambiguous satellite explanations\nBoth overlays fit the displayed tracks; neither is a validated automatic recovery',fontsize=14)
    fig.savefig(ROOT/'trajectories.png',dpi=150);plt.close(fig)
    cs[0].set_ylabel('Fraction of continuity track points');cdf.suptitle('In-sample carrier residual distributions — not position accuracy or held performance',fontsize=13)
    cdf.savefig(ROOT/'carrier-residual-cdf.png',dpi=150);plt.close(cdf)
    (ROOT/'figure-summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
    print(json.dumps(summaries,indent=2))


if __name__=='__main__':main()
