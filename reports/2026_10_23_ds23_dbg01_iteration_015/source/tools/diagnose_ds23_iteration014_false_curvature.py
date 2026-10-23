"""Inspect whole-source failures without changing point membership or polynomials."""

from pathlib import Path
import numpy as np

import run_ds23_dbg01_iteration_014 as runner
from ds23_supported_curvature import curvature_evidence
from run_algo01_ds23_sample import read,write,sha

OUT=runner.RAW/'source_integrity'


def main():
    runner.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve source integrity diagnostic')
    cases=read(runner.RAW/'protocol.json')['cases']
    write(OUT/'protocol.json',dict(cases=cases,source_sha256=sha(Path(__file__)),
        targets='standalone whole-source trials with profile RMS above750Hz in both arms, deduplicated by source',
        original_sources_and_all_IDs_unchanged=True,all_single_deletions_diagnostic_only=True,
        original_gap5cadence_leverage0p9_and_jackknife_curvature_rules_reused=True,
        no_GPS_TLE_or_fit_selected_point_trimming_or_position_fit=True))
    for case in cases:
        d=runner.engine.current_setup(case);trials=read(runner.RAW/'single_curve_reentry'/(case+'_positions.json'))['trials'];seen=set();rows=[]
        for trial in trials:
            if len(trial['additions'])!=1:continue
            component=trial['additions'][0]['component']
            if component in seen:continue
            seen.add(component);gates=[next(g for g in r['gates']['tracks'] if g['component']==component) for r in trial['arms'].values()]
            if not all(g['profile_rms_hz']>750 for g in gates):continue
            t=next(t for t in d['scan'].tracks if t['key']==component);times=np.asarray(t['times']);values=np.asarray(t['values']);degree=t['pieces'][0]['degree'];z=(times-times.mean())/np.ptp(times)
            u=np.polynomial.legendre.legvander(z,degree);q,_=np.linalg.qr(u);leverage=np.sum(q*q,axis=1)
            endpoints=[]
            for removed in [0,len(times)-1]:
                use=np.arange(1,len(times)) if removed==0 else np.arange(len(times)-1);gap=times[1]-times[0] if removed==0 else times[-1]-times[-2]
                if gap>=5*np.median(np.diff(times)) and leverage[removed]>=.9:
                    core=dict(t,times=times[use],values=values[use]);e=curvature_evidence(core)
                    zz=(times-times[use].mean())/np.ptp(times[use]);v=np.polynomial.legendre.legvander(zz,1);b=np.linalg.lstsq(v[use],values[use],rcond=None)[0]
                    endpoints.append(dict(endpoint=removed,core_indices=use,gap_s=float(gap),leverage=float(leverage[removed]),
                        core_curvature=e,linear_core_prediction_hz=v@b,diagnostic_only_no_point_removed=True))
            rows.append(dict(component=component,times=times,values_hz=values,pieces=t['pieces'],observation_ids=t['observation_ids'],
                leverage=leverage,whole_curvature=curvature_evidence(t),isolated_endpoints=endpoints))
        write(OUT/(case+'.json'),dict(case=case,rows=rows,no_point_removed_or_new_position_fit=True))
    write(OUT/'execution.json',dict(all_terminal=True,all_passed=True))


if __name__=='__main__':main()
