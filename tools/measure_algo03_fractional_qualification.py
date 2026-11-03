"""Read-only, bounded qualification via the existing public recording adapters.

Only this orchestration file touches recording readers. Numerical fitters have
no storage dependency. Every selected probe is inherited from a sealed RF-only
qualification plan, with no location or satellite input to the local fit.
"""

import argparse
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import numpy as np

import remeasure_ds23_rx2_cohort as reader
from decoupled_pilot_clocks import ContinuousCoupledWorkspace
from fast_local_pilot_refinement import FastPilotWorkspace
from run_algo01_ds23_sample import ROOT,read,sha


def run(case):
    old=read(reader.OUT/(case+'_refined.json'))
    lookup={r['point']['observation_id']:r for r in old['rows']}
    def fitter(samples,point,fs,qualify=False):
        if not qualify:
            raise ValueError('this read is bounded to sealed qualification probes')
        y=samples[:,0].astype(float)+1j*samples[:,1]
        peak=point['peak'];epoch=peak['integer_epoch_sample']+peak['fractional_epoch_offset_samples']
        previous=lookup[point['observation_id']]['joint_CFO_epoch_rate']
        legacy=FastPilotWorkspace(y,fs,point['edge'],epoch)
        score=float(legacy.evaluate([previous['CFO_hz']],previous['offset_samples'],previous['modulation_ppm'])[0])
        if abs(score-previous['score'])>1e-10:
            raise ValueError('raw observation and legacy likelihood replay failed')
        work=ContinuousCoupledWorkspace(y,fs,point['edge'],epoch)
        fit=work.fast_joint_fit(peak['fractional_tracking_cfo_hz'])
        return dict(point=point,legacy_fit=previous,fractional_fit=fit,
            CFO_change_hz=fit['CFO_hz']-previous['CFO_hz'],score_ratio=fit['score']/previous['score'],
            legacy_likelihood_replay_difference=score-previous['score'])
    # Explicitly supply the new pure fitter to the unchanged bounded adapter
    # orchestration in this process; no source file or archived output changes.
    reader.fit_samples=fitter
    capture=io.StringIO()
    with redirect_stdout(capture):
        reader.measure(case,qualify=True)
    document=json.loads(capture.getvalue())
    document.update(new_fractional_worker_sha256=sha(Path(__file__)),
        new_fractional_fitter_sha256=sha(ROOT/'tools/decoupled_pilot_clocks.py'),
        old_refined_result_sha256=sha(reader.OUT/(case+'_refined.json')),
        no_reference_GPS_TLE_or_satellite_used=True,no_original_CFO_or_contract_written=True)
    print(json.dumps(document,default=lambda v:v.tolist() if isinstance(v,np.ndarray) else v.item()))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
