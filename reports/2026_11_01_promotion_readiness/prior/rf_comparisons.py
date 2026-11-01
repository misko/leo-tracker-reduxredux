"""Two RF-defined contextual comparisons; no extra parameter fitting."""
from pathlib import Path
import time
import ablate as a


def main():
    out=a.OUT/'rf_comparisons';out.mkdir(exist_ok=True)
    candidates=[]
    for path in sorted(a.SOURCE.glob('DS*/result.json')):
        r=a.e.read(path)
        for row in r.get('history_records',[]):
            if row.get('accepted') and r['case']!='DS26-0058':
                candidates.append(dict(case=r['case'],minimum_paired_RF_gain=min(row['gains'].values()),
                    gains=row['gains'],source=str(path),sha256=a.e.sha(path)))
    candidates.sort(key=lambda r:(-r['minimum_paired_RF_gain'],r['case']))
    selected=candidates[:2]
    a.e.write(out/'spec.json',dict(created_utc_ns=time.time_ns(),
        rule='Top two other accepted history-only scans by minimum normalized RF gain across c arms; no position error used',
        selected=selected,all_eligible=candidates,
        comparison='Exact saved matched two-start c-arm endpoints plus new fixed-position component-score audit; no new refits or independent validation',
        cells=['original','width','radial','cross','predictive','complete'],code_sha256=a.e.sha(__file__)))
    for item in selected:
        case=item['case'];folder=out/case;folder.mkdir(exist_ok=True)
        a.e.rec.CATALOGUES=a.e.ROOTS[case[:4]]/'catalogues'
        d,z,replay=a.e.load_case(case)
        source=a.SOURCE/case
        a.e.write(folder/'export.json',a.e.read(source/'incumbent_history/export.json'))
        hd,history=a.e.complete_history(d,z,case,a.e.active_ids(d),folder)
        receipt={}
        for cell in ('original','width','radial','cross','predictive','complete'):
            dd=a.mixed(d,hd,z,a.CELLS[cell]);receipt[cell]={}
            for arm,(p,x) in dd['problems'].items():
                receipt[cell][arm]=dict(fixed_position_objective=a.e.objective(p,dd,x),
                    calibration_priors=[dict(norad=int(p.scan.norads[j]),width_s=float(p.phase_sigma[k]),mean_s=float(dd['means'][k])) for k,j in enumerate(p.labels)],
                    orbit_metadata=p.mode_metadata,predictive_priors=[f.receipt for f in dd['families']])
        record=a.e.read(source/'result.json')['history_records'][0]
        control=a.e.paired(a.e.read(source/'history_control.json'))
        endpoints={}
        for arm in a.e.ARMS:
            old,new=control[arm],record['pair'][arm]
            endpoints[arm]=dict(original_error_m=old['error_m'],history_error_m=new['error_m'],
                delta_error_m=new['error_m']-old['error_m'],original_objective=old['objective'],
                history_objective=new['objective'],delta_objective=new['objective']-old['objective'],
                original_rms_hz=old['rms_hz'],history_rms_hz=new['rms_hz'])
        a.e.write(folder/'result.json',dict(case=case,RF_selection=item,replay=replay,history=history,
            component_audit=receipt,saved_matched_endpoints=endpoints,independent_validation=False))
        print(case,endpoints,flush=True)


if __name__=='__main__':main()
