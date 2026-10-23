"""Report-only GPS and residual plots; never used by the fitting script."""
import run_followup as f
from report_full import position_error
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
    r=f.s.read(f.OUT/'results.json');rows=[]
    fig,axes=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for j,(arm,fits) in enumerate(r['path_endpoint_diagnostics'].items()):
        fits=dict(fits,excluded_path_endpoint=r['ablation'][arm]['common_full_mask_endpoint'])
        for label,v in fits.items():
            axes[0,j].plot(v['times_s'],v['raw_prediction_residual_hz'],'.-',label=label)
            axes[1,j].plot(v['times_s'],v['centered_raw_prediction_residual_hz'],'.-',label=label)
        a=r['ablation'][arm];s=a['summary'];full=a['common_full_mask_endpoint']['full_mask_endpoint']
        rows.append(dict(arm=arm,endpoint_east_north_km=s['endpoint_east_north_km'],
            position_error_km_report_only=position_error(s['endpoint_latlon']),qualified=s['qualified'],
            reduced_objective=s['negative_twice_elbo'],full_mask_objective=full['negative_twice_elbo'],
            reduced_minimum_gate_slack=s['minimum_gate_slack'],full_mask_minimum_gate_slack=full['minimum_gate_slack'],
            full_mask_failing_gates=full['failing_gates'],RMS_hz=s['RMS_hz'],associated_points=a['coverage']['associated'],
            original_parent_ids_preserved=a['original_parent_ids_preserved'],seconds=a['seconds']))
        axes[0,j].set(title=arm+' raw prediction residual',ylabel='Hz')
        axes[1,j].set(title=arm+' centered raw residual',ylabel='Hz',xlabel='Time (s)')
        for ax in axes[:,j]:ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('RF-selected new path GRAPH_PATH_persistent5s_005 · NORAD68553 · diagnostic exclusion')
    fig.savefig(f.OUT/'offending_path_residuals.png',dpi=150);plt.close(fig)
    f.s.write(f.OUT/'summary.json',dict(rows=rows,interpretation='Exact new path RF-selected by sole failing gate; diagnostic exclusion only. Full and reduced objectives have different data and must not be compared directly; common full-mask objective is provided. GPS errors reporting-only.'))
if __name__=='__main__':main()
