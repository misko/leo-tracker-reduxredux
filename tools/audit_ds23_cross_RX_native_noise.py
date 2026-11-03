"""Polynomial residual covariance of frame-matched native receiver peaks.

This diagnoses the independence assumption without orbit or position fits.
Degree4 is fixed, no curve is chosen by observed correlation, and no covariance
is advertised as a calibrated measurement-error estimate.
"""

from collections import defaultdict,Counter
import numpy as np
from inventory_ds23_cross_RX_curves import SOURCE,TRACKING
from ds23_same_probe_covariance import residual_pair
from ds23_frame_registration import PERIOD
from run_algo01_ds23_sample import ROOT,read,write,sha


def main():
    source=read(SOURCE);result=[];ambiguous=0
    for case in source['rows']:
        observations=read(TRACKING/case['case']/'observations.json');frequency=defaultdict(set)
        for o in observations:frequency[round(o['time_s'],6),o['channel']].add(o['actual_rf_hz'])
        groups=defaultdict(list)
        for row in case['paired_points']:
            available=frequency[round(row['time_s'],6),row['channel']]
            if len(available)!=1:raise ValueError('native pair RF is ambiguous')
            groups[row['norad'],row['channel'],next(iter(available))].append(row)
        for key,rows in groups.items():
            counts=Counter(r['time_s'] for r in rows)
            ambiguous+=sum(v for v in counts.values() if v>1)
            rows=[r for r in rows if counts[r['time_s']]==1]
            rows.sort(key=lambda r:r['time_s']);t=np.array([r['time_s'] for r in rows])
            if len(rows)<20 or np.ptp(t)<20.:continue
            # Never unwrap across a very long gap in paired reception support.
            for ix in np.split(np.arange(len(t)),np.flatnonzero(np.diff(t)>10.)+1):
                if len(ix)<20 or np.ptp(t[ix])<20.:continue
                y=np.array([[r['native_peaks'][k]['cfo'] for r in rows] for k in [0,1]])[:,ix]
                y=np.unwrap(y*2*np.pi/PERIOD,axis=1)*PERIOD/(2*np.pi)
                statistics=residual_pair(t[ix],y[0],y[1],4)
                result.append(dict(case=case['case'],norad=key[0],channel=key[1],rf_hz=key[2],points=len(ix),
                    span_s=float(np.ptp(t[ix])),statistics=statistics))
    out=ROOT/'reports/2026_10_21_ds23_cross_RX_curves_v2'
    write(out/'native_noise_covariance_audit.json',dict(rows=result,all_eligible_curves_reported=True,ambiguous_simultaneous_family_pairs_excluded=ambiguous,
        fixed_polynomial_degree=4,no_GPS_or_orbital_position_in_fit=True,
        median_correlation=float(np.median([r['statistics']['correlation'] for r in result])),
        median_differential_to_independent_noise_ratio=float(np.median([r['statistics']['difference_sigma_hz']/r['statistics']['independent_difference_sigma_hz'] for r in result])),
        source_pairs_sha256=sha(SOURCE),no_calibrated_covariance_or_position_improvement_claim=True))
    print(dict(curves=len(result),median_rho=np.median([r['statistics']['correlation'] for r in result]),
        median_ratio=np.median([r['statistics']['difference_sigma_hz']/r['statistics']['independent_difference_sigma_hz'] for r in result])),flush=True)


if __name__=='__main__':main()
