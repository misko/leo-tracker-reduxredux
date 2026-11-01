"""Native-point residual figures and a conditional, fixed-identity loss map."""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from prototype import OUT,PRIOR,INPUT,read,write,reconstruct,candidate,build,objective,gate_slacks
from summarize import best

def render_tracks(case,new,weight,constrained):
    trial=read(OUT/case/(f'{new}-w{weight:g}-'+('constrained' if constrained else 'free')+'.json'))
    r=best(trial,'fitted_c',False);old=trial['old_norad']
    native=np.load(PRIOR/case/'fitted_c-native-fit.npz');base_res=native['residual'][native['keep']];values=native['values'][native['keep']]
    offsets=np.r_[0,np.cumsum([len(t['times_s']) for t in r['tracks']])];assert offsets[-1]==len(base_res)
    target=[(t,slice(offsets[k],offsets[k+1])) for k,t in enumerate(r['tracks']) if t['norad']==new]
    fig,axs=plt.subplots(len(target),2,figsize=(12,2.3*len(target)),squeeze=False)
    for (t,sl),ax in zip(target,axs):
        times=np.asarray(t['times_s']);v=values[sl];rr=np.asarray(t['residual_hz']);br=base_res[sl]
        ax[0].scatter(times,v/1000,s=8,c='black',label='Native GLRT, original alias branch')
        ax[0].plot(times,(v-br)/1000,c='tab:red',label=f'Published adjusted orbit ({old})')
        ax[0].plot(times,(v-rr)/1000,c='tab:blue',ls='--',label=f'Prototype adjusted orbit ({new})')
        ax[0].set(ylabel='CFO (kHz)',title=t['component'])
        ax[1].plot(times,br,'.-',ms=3,c='tab:red',label='Published residual')
        ax[1].plot(times,rr,'.-',ms=3,c='tab:blue',label='Prototype residual');ax[1].axhline(0,c='black',lw=.7)
        ax[1].set(ylabel='Residual (Hz)',title=f"Prototype RMS {np.sqrt(np.mean(rr**2)):.1f} Hz")
        for a in ax:a.grid(alpha=.2)
    for a in axs[-1]:a.set_xlabel('Scan time (s)')
    for a in axs[0]:a.legend(fontsize=7)
    fig.suptitle(f"{case}: {old} → {new}; weight {weight}; {'gate-constrained' if constrained else 'unconstrained'}\nFitted c; screened={r['qualified']}; error={r['error_m']/1000:.3f} km. All native points retained in fitting.")
    fig.tight_layout();fig.savefig(OUT/case/'target_curves.png',dpi=160);plt.close(fig)

def conflict():
    case='DS26-0034';free=best(read(OUT/case/'59188-w1-free.json'),'fitted_c',False);bounded=best(read(OUT/case/'59188-w1-constrained.json'),'fitted_c')
    key='RX1-CH1-T002'
    targets=[t for t in free['tracks'] if t['norad']==69188 and 'T002' in t['component']]
    assert len(targets)==1
    first=targets[0];key=first['component'];second=next(t for t in bounded['tracks'] if t['component']==key)
    fig,ax=plt.subplots(figsize=(9,4));t=first['times_s']
    ax.plot(t,first['residual_hz'],'o-',ms=3,label='Unconstrained replacement: fails slope + curvature')
    ax.plot(t,second['residual_hz'],'o-',ms=3,label='Gate-constrained replacement: passes')
    ax.axhline(0,c='k',lw=.8);ax.set(xlabel='Scan time (s)',ylabel='Conditional residual (Hz)',title=f'{case}: protecting incumbent {key}, NORAD 69188')
    ax.legend(fontsize=9);ax.grid(alpha=.2);fig.tight_layout();fig.savefig(OUT/case/'conflicting_track.png',dpi=170);plt.close(fig)
    z=read(INPUT/(case+'.json'));d=candidate(reconstruct(z),z,case,59188,1.)
    p,dd=build(d,z,'fitted_c',np.asarray(bounded['reference']))
    # Grid is centered on inferred endpoints, never on truth; truth marked only afterwards.
    coords=np.array([free['x'],bounded['x']]);lo=coords.min(axis=0)-2.;hi=coords.max(axis=0)+2.
    east=np.linspace(lo[0],hi[0],35);north=np.linspace(lo[1],hi[1],35);score=np.empty((35,35));slack=score.copy()
    for i,n in enumerate(north):
        for j,e in enumerate(east):
            x=np.array([e,n]);score[i,j]=objective(p,dd,x);slack[i,j]=min(gate_slacks(p,x,dd['entries']).values())
    write(OUT/case/'conditional_surface.json',dict(east_km=east,north_km=north,objective=score,minimum_gate_slack=slack,
        phase_reference=bounded['reference'],fixed_identity=59188,scope='profile radio/orbital coefficients, frozen phase reference and ownership; NOT full pipeline reruns'))
    fig,ax=plt.subplots(figsize=(8,6));mesh=ax.pcolormesh(east,north,np.minimum(score-score.min(),60),shading='auto',cmap='viridis')
    ax.contourf(east,north,slack,levels=[-1e9,0],colors=['none'],hatches=['///'])
    ax.contour(east,north,slack,levels=[0],colors='white',linewidths=1.5)
    for r,marker,col,label in [(free,'x','red','Unconstrained fit'),(bounded,'o','cyan','Gate-constrained fit')]:
        ax.scatter(*r['x'],c=col,marker=marker,s=80,label=label)
    from diagnose import SITE_X
    ax.scatter(*SITE_X,c='white',edgecolors='black',marker='*',s=180,label='Evaluation site (not used to fit)')
    fig.colorbar(mesh,ax=ax,label='Δ RF objective (clipped at 60)');ax.set(xlabel='East from configured box center (km)',ylabel='North from configured box center (km)',title='DS26-0034, NORAD 59188 hypothesis\nHatching: at least one unchanged RF gate fails')
    ax.legend(fontsize=8);fig.tight_layout();fig.savefig(OUT/case/'conditional_surface.png',dpi=170);plt.close(fig)

if __name__=='__main__':
    for args in [('DS26-0203',67935,.25,False),('DS26-0070',67047,1.,False),('DS26-0251',58787,1.,True),('DS26-0034',59188,1.,True)]:render_tracks(*args)
    conflict()
