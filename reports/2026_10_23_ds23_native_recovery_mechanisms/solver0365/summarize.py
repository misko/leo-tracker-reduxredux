"""Reporting only: GPS error, gate/coverage audits and phase trajectories."""
import run_solver as s
from report_full import position_error
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
    data=s.read(s.OUT/'results.json');rows=[]
    for record in data['cases']:
        case=record['case'];d,kind,primary,frozen,_=s.setup(case)
        for fit in record['fits']:
            if 'summary' not in fit:continue
            a=fit['arm'];r=fit['summary'];cov=s.exp.paths.coverage(d,kind,a,r)
            preserves=set(frozen['ordinary_graph']['coverage'][a]['accepted_observation_ids'])<=set(cov['accepted_observation_ids'])
            row=dict(case=case,arm=a,solver=fit['solver'],position_error_km_report_only=position_error(r['endpoint_latlon']),
                negative_twice_elbo=r['negative_twice_elbo'],RMS_hz=r['RMS_hz'],minimum_gate_slack=r['minimum_gate_slack'],
                failing_gates=r['failing_gates'],phase_change_s=r['final_phase_change_s'],
                original_parent_ids_preserved=preserves,associated_points=cov['associated'],qualified=bool(r['qualified'] and preserves),
                endpoint_east_north_km=r['endpoint_east_north_km'],seconds=fit['seconds'])
            rows.append(row)
    pairs=[]
    for case in data['protocol']['cases']:
        for a in ['c0','fitted_c']:
            ordinary=next(r for r in rows if r['case']==case and r['arm']==a and r['solver']=='ordinary')
            constrained=next(r for r in rows if r['case']==case and r['arm']==a and r['solver']=='constrained')
            pairs.append(dict(case=case,arm=a,constrained_minus_ordinary={k:constrained[k]-ordinary[k] for k in ['position_error_km_report_only','negative_twice_elbo','RMS_hz','associated_points']},
                ordinary_qualified=ordinary['qualified'],constrained_qualified=constrained['qualified']))
    s.write(s.OUT/'summary.json',dict(rows=rows,comparisons=pairs,
        interpretation='RF fits use no GPS. Position errors are reporting-only. Failing rows are diagnostics and not proposed accepted solutions.'))
    fig,axes=plt.subplots(len(data['cases']),2,figsize=(12,4*len(data['cases'])),squeeze=False,layout='constrained')
    for i,case in enumerate(data['cases']):
        for j,a in enumerate(['c0','fitted_c']):
            ax=axes[i,j]
            for fit in case['fits']:
                if fit['arm']!=a or 'summary' not in fit:continue
                points=[fit['start']]+[h['after']['endpoint_east_north_km'] for h in fit['history']]
                ax.plot([p[0] for p in points],[p[1] for p in points],'-o',label=fit['solver'])
                for n,p in enumerate(points):ax.annotate(str(n),p,fontsize=7)
            ax.set(title=case['case']+' '+a,xlabel='East (km)',ylabel='North (km)');ax.grid(alpha=.25);ax.legend()
    fig.suptitle('Identical native-mask endpoints: matched 5 × 40 phase trajectories; no GPS plotted')
    fig.savefig(s.OUT/'trajectories.png',dpi=150);plt.close(fig)
if __name__=='__main__':main()
