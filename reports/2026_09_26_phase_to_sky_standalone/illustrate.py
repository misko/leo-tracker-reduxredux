"""Rebuild standalone teaching figures and seeded whole-group benchmark."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from geometry import incidence_projection, wrap_radians, C_M_PER_S, TAU
from scoring import fit_single_candidate

HERE = Path(__file__).resolve().parent

def save(fig, name):
    fig.tight_layout()
    for suffix in ('png', 'svg'):
        fig.savefig(HERE / f'{name}.{suffix}', dpi=160, bbox_inches='tight')
    plt.close(fig)

def main():
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    ax = axes[0]
    ax.scatter([0, 1], [0, 0], s=180, c=['#1768ac', '#d1495b'])
    ax.text(0, -.17, 'LNB 0 / RX0', ha='center')
    ax.text(1, -.17, 'LNB 1 / RX1', ha='center')
    ax.annotate('', xy=(1, -.35), xytext=(0, -.35), arrowprops=dict(arrowstyle='<->'))
    ax.text(.5, -.46, 'Baseline B, axis azimuth 79°', ha='center')
    direction=np.array([.6, .8])
    for x in (0, 1):
        ax.annotate('', xy=(x, .07), xytext=(x+.6, .87), arrowprops=dict(arrowstyle='->', color='#777777', lw=2))
    ax.annotate('toward satellite: s', xy=(.6,.8), xytext=(-.2,1.1))
    ax.plot([1,.36],[0,.48], '--', color='#2a9d8f')
    ax.plot([0,.36],[0,.48], color='#2a9d8f', lw=4)
    ax.text(.1,.55,'B · s = projected path', color='#187a70')
    ax.set(xlim=(-.4,1.8), ylim=(-.6,1.3), aspect='equal', title='Illustrative baseline projection')
    ax.axis('off')
    az=np.linspace(0,360,361)
    for elevation in (10,40,70):
        axes[1].plot(az, incidence_projection(az,elevation), label=f'elevation {elevation}°')
    axes[1].set(xlabel='Satellite azimuth (deg, clockwise from north)', ylabel='Projection u = cos(el) cos(az − 79°)', title='One baseline measures one direction component')
    axes[1].legend(); axes[1].grid(alpha=.25)
    save(fig,'how-geometry-works')

    t=np.linspace(0,1,500)
    geo_a=.25+.35*t; geo_b=-.25+.15*t
    hardware=1.2*np.sin(8*t)+.4*t
    fig, axes=plt.subplots(1,3,figsize=(13,3.8))
    axes[0].plot(t,geo_a,label='signal A geometry');axes[0].plot(t,geo_b,label='signal B geometry')
    axes[1].plot(t,geo_a+hardware,label='measured A');axes[1].plot(t,geo_b+hardware,label='measured B')
    axes[2].plot(t,(geo_b+hardware)-(geo_a+hardware),label='B − A',lw=3)
    for ax,title in zip(axes,['Geometric phase','Same hardware term added','Shared hardware term cancels']):
        ax.set(xlabel='Illustrative time',ylabel='Unwrapped phase (rad)',title=title);ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.suptitle('Idealized simultaneous signals: frequency-dependent delay and signal bias can remain')
    save(fig,'how-cancellation-works')

    rng=np.random.default_rng(20260926)
    n=42;t=np.linspace(0,1,n);groups=np.arange(n)//3
    held_groups=sorted(rng.choice(np.unique(groups),5,replace=False).tolist())
    train=~np.isin(groups,held_groups)
    az=24+96*t;el=18+48*np.sin(np.pi*t)
    rf=np.choose(np.arange(n)%3,[10.94e9,11.19e9,11.69e9])
    truth=incidence_projection(az,el)
    phase=wrap_radians(TAU*.79*rf*truth/C_M_PER_S+.48+rng.normal(0,.035,n))
    candidates={'True direction':truth,'Azimuth +18°':incidence_projection(az+18,el),'Elevation −12°':incidence_projection(az,el-12),'Different pass':incidence_projection(155-70*t,25+30*np.sin(np.pi*t))}
    results={};fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    for name, projection in candidates.items():
        fit=fit_single_candidate(phase,projection,rf,train,np.linspace(.45,1.1,2601))
        residual=fit.pop('residual_phase_rad')
        fit['held_rms_deg']=float(np.degrees(np.sqrt(np.mean(residual[~train]**2))))
        results[name]=fit
        axes[0].scatter(t[~train],np.degrees(residual[~train]),label=name,s=25)
    axes[0].set(xlabel='Synthetic pass time (normalized)',ylabel='Held wrapped residual (deg)',title='Predict held groups after fitting training groups')
    axes[0].legend(fontsize=8);axes[0].grid(alpha=.2)
    axes[1].bar(list(results),[r['held_loss'] for r in results.values()],color=['#2a9d8f','#e9c46a','#f4a261','#e76f51'])
    axes[1].set(ylabel='Held circular loss (lower is better)',title='Every candidate fits its own B and constant phase')
    axes[1].tick_params(axis='x',rotation=20)
    save(fig,'how-candidate-scoring-works')
    output=dict(seed=20260926,split='random whole groups of three observations',held_groups=held_groups,group_assignments=groups.tolist(),train_mask=train.tolist(),truth=dict(baseline_m=.79,beta_rad=.48,noise_std_rad=.035),results=results)
    (HERE/'randomized-benchmark.json').write_text(json.dumps(output,indent=2)+'\n')
    assert results['True direction']['held_loss'] < min(r['held_loss'] for n,r in results.items() if n!='True direction')
    print(json.dumps(output['results'],indent=2))

if __name__=='__main__': main()
