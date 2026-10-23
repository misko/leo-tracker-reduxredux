"""Position accuracy added only after fits; no cross-variance score selection."""
import run_bias as b
from report_full import position_error
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
def main():
    result=b.s.read(b.OUT/'results.json');rows=[]
    fig,axes=plt.subplots(1,3,figsize=(14,4),layout='constrained')
    for ax,case in zip(axes,result['cases'],strict=True):
        for fit in case['fits']:
            s=fit['summary'];rows.append(dict(case=case['case'],arm=fit['arm'],native_bias_sigma_hz=fit['native_bias_sigma_hz'],
                position_error_km_report_only=position_error(s['endpoint_latlon']),endpoint_east_north_km=s['endpoint_east_north_km'],
                own_objective=s['negative_twice_elbo'],common_sigma300_objective=fit['common_sigma300']['negative_twice_elbo'],
                minimum_gate_slack=s['minimum_gate_slack'],RMS_hz=s['RMS_hz'],associated_points=fit['coverage']['associated'],
                original_parent_ids_preserved=fit['original_parent_ids_preserved'],qualified=fit['qualified'],seconds=fit['seconds']))
        for arm in ['c0','fitted_c']:
            subset=[r for r in rows if r['case']==case['case'] and r['arm']==arm]
            ax.plot([r['native_bias_sigma_hz'] for r in subset],[r['position_error_km_report_only'] for r in subset],'-o',label=arm)
        ax.set(xscale='log',xlabel='New native path offset prior SD (Hz)',ylabel='Position error (km), report only',title=case['case']);ax.legend();ax.grid(alpha=.2)
    fig.suptitle('Predeclared variance diagnostic · original predictive entries remain at 300 Hz')
    fig.savefig(b.OUT/'position_diagnostic.png',dpi=150);plt.close(fig)
    b.s.write(b.OUT/'summary.json',dict(rows=rows,interpretation='No GPS inference or parameter selection. 600Hz diagnostic not promoted;3000Hz extreme only. Own objectives across variance settings have different normalizations; common sigma300 score provided for comparison.'))
if __name__=='__main__':main()
