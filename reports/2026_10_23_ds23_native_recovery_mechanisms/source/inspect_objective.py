"""Fixed-observation endpoint comparisons and conditional influence diagnostics."""
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mechanism import OUT,FROZEN,ARMS,load,append,id_audit,exp,read,write
sys.path.insert(0,str(OUT/'audit'))
from diagnostics import decompose,conditional_gradients
from ds23_predictive_linear import linear_geometry
from probe_algo03_feasible_recovery import gate_slacks

TERMS=('curved_objective','predictive_quadratic','predictive_logdet','predictive_normalization','predictive_objective','total_objective')

def compact(c):return {k:float(c[k]) for k in TERMS+('replay_difference',)}

def evaluate(d,kind,arm,saved):
    p=exp.paths.build(d,kind,arm,saved['phase_reference']);x=np.asarray(saved['endpoint_east_north_km'])
    c=decompose(p,x,d['powers'])
    return p,c

def refresh_at_position(d,kind,arm,x,reference):
    history=[]
    for _ in range(5):
        p=exp.paths.build(d,kind,arm,reference)
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(float(np.max(abs(phase-reference))));reference=phase
    return p,history

def case_analysis(case):
    parent,kind,fragments,record=load(case);full=append(parent,fragments)
    output=dict(case=case,arms={},native_paths=fragments,
        gradient_condition='fixed saved phase reference; curved nuisance posterior recomputed at perturbation',
        full_mask_scores_common_observations=True)
    chart,axes=plt.subplots(len(fragments),2,figsize=(13,2.4*len(fragments)),squeeze=False)
    for arm in ARMS:
        rows={};grads={};audits={};dense={}
        for name,saved in [('graph',record['ordinary_graph']['arms'][arm]),('final',record['final']['arms'][arm])]:
            p,c=evaluate(full,kind,arm,saved);dense[name]=c
            rows[name]=compact(c);rows[name]['endpoint_east_north_km']=saved['endpoint_east_north_km']
            grads[name]=conditional_gradients(p,np.asarray(saved['endpoint_east_north_km']),full['powers'])
            audits[name]=id_audit(p,full['entries'])
            if arm=='fitted_c':
                view,values,sigma,groups,slices=linear_geometry(p,full['entries'])
                for i,(entry,sl) in enumerate(zip(full['entries'],slices,strict=True)):
                    matches=[j for j,f in enumerate(fragments) if f['key']==entry['component']]
                    if not matches:continue
                    j=matches[0];f=fragments[j];times=view.flat_times[sl]
                    raw=c['raw_residual_hz'][sl];mean=values[sl]-raw
                    color='tab:blue' if name=='graph' else 'tab:red'
                    if name=='graph':axes[j,0].scatter(times,values[sl]/1000,s=9,c='black',label='Native GLRT')
                    axes[j,0].plot(times,mean/1000,color=color,label=name+' orbit + radio prediction')
                    axes[j,1].plot(times,raw,'.-',color=color,label=name+' raw residual')
                    axes[j,0].set_title(f"{f['norad']} RX{f['receiver']} CH{f['channel']} — {len(times)} points",fontsize=9)
                    axes[j,0].set_ylabel('Unwrapped CFO, kHz');axes[j,1].set_ylabel('Raw residual, Hz')
        # Conditional contribution: full joint score minus the same score without
        # one new family. Such contributions are not additive under correlation.
        s=record['ordinary_graph']['arms'][arm];x=np.asarray(s['endpoint_east_north_km'])
        p0,c0=evaluate(parent,kind,arm,s);g0=conditional_gradients(p0,x,parent['powers'])
        family=[]
        for norad in sorted({f['norad'] for f in fragments}):
            without=append(parent,[f for f in fragments if f['norad']!=norad])
            pp,cc=evaluate(without,kind,arm,s);gg=conditional_gradients(pp,x,without['powers'])
            gradient=np.array(grads['graph']['gradients']['total_objective'])-gg['gradients']['total_objective']
            family.append(dict(norad=norad,points=sum(len(f['times']) for f in fragments if f['norad']==norad),
                conditional_added_score=rows['graph']['total_objective']-cc['total_objective'],
                conditional_gradient=gradient,
                label='full minus without new family, at fixed graph phase; correlated contributions not additive'))
        # Phase-refreshed line between existing graph and final endpoints, common
        # full mask throughout. This is not a complete regional search.
        line=[];a=np.asarray(s['endpoint_east_north_km']);b=np.asarray(record['final']['arms'][arm]['endpoint_east_north_km'])
        for fraction in np.linspace(0,1,11):
            x=a+fraction*(b-a);p,history=refresh_at_position(full,kind,arm,x,np.asarray(s['phase_reference']))
            c=decompose(p,x,full['powers']);gates=gate_slacks(p,x,full['entries'])
            line.append(dict(fraction=float(fraction),position=x,terms=compact(c),phase_change_s=history[-1],
                minimum_gate_slack=min(gates.values())))
        output['arms'][arm]=dict(endpoints=rows,gradients=grads,parent_at_graph=compact(c0),parent_gradient=g0,
            family_conditional_influence=family,id_audits=audits,line=line)
    for ax in axes.flat:ax.grid(alpha=.2);ax.set_xlabel('Scan time, s')
    axes[0,0].legend(fontsize=7);axes[0,1].legend(fontsize=7)
    chart.suptitle(case+' — same native points, saved graph versus final position (fitted c)',fontsize=12)
    chart.tight_layout();chart.savefig(OUT/'figures'/(case+'_native_CFO_residuals.png'),dpi=150);plt.close(chart)
    # Score each ablated0259 endpoint on the original full common mask.
    if case=='DS23-0259':
        output['common_full_mask_scores']=[]
        for path in sorted((OUT/'raw').glob(case+'*/result.json')):
            trial=read(path)
            if trial['status']!='complete':continue
            for arm,saved in trial['arms'].items():
                p,c=evaluate(full,kind,arm,saved)
                output['common_full_mask_scores'].append(dict(name=trial['job']['name'],arm=arm,
                    position=saved['endpoint_east_north_km'],terms=compact(c),
                    full_mask_minimum_gate_slack=min(gate_slacks(p,np.asarray(saved['endpoint_east_north_km']),full['entries']).values())))
    write(OUT/'evidence'/(case+'_objective.json'),output)
    return output

def figures(results):
    fig,axes=plt.subplots(2,2,figsize=(12,8))
    for row,result in enumerate(results):
        for col,arm in enumerate(ARMS):
            a=result['arms'][arm];line=a['line'];ax=axes[row,col]
            for key in ['curved_objective','predictive_quadratic','predictive_logdet','total_objective']:
                vals=np.array([r['terms'][key] for r in line]);ax.plot([r['fraction'] for r in line],vals-vals[0],label=key)
            ax.set_title(result['case']+' '+arm);ax.set_xlabel('Fraction from graph to published final position');ax.set_ylabel('Change in common-mask objective');ax.grid(alpha=.2)
    axes[0,0].legend(fontsize=8);fig.tight_layout();fig.savefig(OUT/'figures/objective_components.png',dpi=160);plt.close(fig)

if __name__=='__main__':
    (OUT/'figures').mkdir(exist_ok=True);(OUT/'evidence').mkdir(exist_ok=True)
    results=[case_analysis(c) for c in ['DS23-0259','DS23-0365']]
    figures(results)
    print('Completed common-mask objective replay, family gradients, ID audits, and CFO/residual figures.',flush=True)
