"""Synthetic delay-sign check of the public GLRT scorer; no captured IQ used.

This verifies an integer epoch convention, not transmitter clocks, fractional
timing accuracy, or a model relating actual beam timing to geometric range.
"""

from pathlib import Path
import numpy as np

from leo.analysis.starlink.fast_scan_scores import conditioned_glrt64_scores
from leo.analysis.starlink.pilot_predictor import pilot_period
from run_algo01_ds23_sample import ROOT,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_counter_time_audit'


def main():
    OUT.mkdir(exist_ok=True);rows=[]
    for edge in ('lower','upper'):
        for cfo in (-125000.,125000.):
            estimates=[]
            for delay in (217,219):
                z=np.tile(np.roll(pilot_period(edge),delay),5)
                z*=np.exp(2j*np.pi*cfo*np.arange(len(z))/2500000.)
                epochs=tuple(range(delay-3,delay+4))
                scores=conditioned_glrt64_scores(z,2500000,epoch_samples=epochs,
                    acquired_cfo_hz=(cfo,)*len(epochs),edge=edge)
                k=max(range(len(scores)),key=lambda k:scores[k].exact_score)
                estimates.append(epochs[k])
                rows.append(dict(edge=edge,cfo_hz=cfo,planted_delay_samples=delay,
                    estimated_epoch_sample=epochs[k],trial_epochs=epochs,
                    exact_scores=[s.exact_score for s in scores]))
            if estimates!=[217,219]:raise ValueError('positive planted delay did not produce positive epoch shift')
    write(OUT/'synthetic_epoch_sign.json',dict(rows=rows,all_eight_cases_passed=True,
        positive_integer_delay_means_later_reported_epoch=True,
        real_frame_clock_range_sign_not_determined=True,
        no_IQ_capture_GPS_TLE_or_new_RF_used=True,source_sha256=sha(Path(__file__)),
        scorer_source_sha256=sha(ROOT/'src/leo/analysis/starlink/fast_scan_scores.py')))
    print('Eight synthetic integer-delay/CFO/edge cases passed',flush=True)


if __name__=='__main__':
    main()
