"""Predeclared11-case public fractional scorer check; no acquisition/model fit."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import time
import unittest
import numpy as np
from synthetic import waveform,cases,FS,SAMPLES,TRUE_EPOCH

HERE=Path(__file__).resolve().parent
PINNED=Path('/opt/leo-fast-auto/f141dbb30321bc8f9e8183576c511431ea60a6b3/worker/src/leo')
REPORTS=HERE.parents[1]
def digest(p):return 'sha256:'+hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):
    with Path(p).open('x') as stream:json.dump(v,stream,indent=2,allow_nan=False);stream.write('\n')


def run():
    begun=time.monotonic();deadline=begun+60
    source=[PINNED/p for p in ['scanner/fast_scan_detector.py','scanner/detector.py','analysis/starlink/acquisition.py',
        'analysis/starlink/fast_scan_scores.py','analysis/starlink/fast_scan_fractional.py','analysis/starlink/pilot_methods.py',
        'analysis/starlink/fractional_epoch.py','analysis/starlink/templates.py','application/scanner_trajectory.py','contracts/scanner_tracking.py']]
    sources=source+[HERE/'run.py',HERE/'synthetic.py',HERE/'test_synthetic.py',
        REPORTS/'three-track-20261016/scripts/within_frame_scale_control.py',REPORTS/'three-track-20261016/scripts/late_within_frame_scale.py',
        REPORTS/'three-track-20261016/evidence/within_frame_scale_control.json',REPORTS/'three-track-20261016/evidence/late_within_frame_scale.json']
    save(HERE/'protocol.json',dict(purpose='Currentpinnedpublicscorer factorizedcarrier/epoch/modulationwarp audit; notold detector-byte attestation',
        maximum_seconds=60,maximum_refine_calls=11,maximum_candidate_glrt_scores=66,fs_hz=FS,sample_count=SAMPLES,true_epoch_samples=TRUE_EPOCH,
        fixed_anchor=500,frame_lattice='TRUE_EPOCH+round(frame*Fs/750), independentcarrier; nominalframeperiodnotwarped',
        injection='Templatequery=local/(1+warp), pivotframeepoch; carriercomplexrotation AFTERmodulationwarp; noRF/Fsconstraint',
        stress='±2000ppm modulation-clockstress,notmeasuredDSXerrororphysicalADC/propagationclockmodel; cannotquantifyrealcoupling',
        cases=cases(),method='Publicfast_scan_scores.refine_glrt64_epochs, knownintegeranchor andconditioning input; notfullcoarseacquisition or prototypejoint_refine',
        cost='Eachrefinecall5timinggridcandidateGLRTscores+atmost1fractionalclosure; retainunbracketed/failure,noextrasweep/retry',
        limits='No realIQ, corpuscampaign, orbit/localizationfit, reference read, runtimeedit, monkeypatch, old/tmp execution orphysicalprecompensationclaim',
        source_sha256={str(p):digest(p) for p in sources}))
    import test_synthetic
    tests=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(test_synthetic))
    if not tests.wasSuccessful():raise AssertionError('Injection tests failed')
    from leo.analysis.starlink.fast_scan_scores import refine_glrt64_epochs
    outcomes=[];candidate_scores=0
    for index,case in enumerate(cases()):
        if time.monotonic()>=deadline:raise TimeoutError('Synthetic60s allowance')
        samples=waveform(case['carrier_hz'],case['warp_ppm']);started=time.monotonic()
        row=dict(case,iq_sha256='sha256:'+hashlib.sha256(samples.tobytes()).hexdigest(),sample_count=len(samples))
        try:
            result=refine_glrt64_epochs(samples,FS,integer_epoch_samples=(500,),
                acquired_cfo_hz=(case['conditioning_cfo_hz'],),edge='lower')[0]
            candidate_scores+=5+int(result.fractional_epoch_offset_samples is not None)
            raw=asdict(result);raw['status']=result.status.value
            row.update(result=raw,scorer_elapsed_seconds=time.monotonic()-started,
                estimated_epoch_samples=None if result.fractional_epoch_offset_samples is None else 500+result.fractional_epoch_offset_samples,
                epoch_error_samples=None if result.fractional_epoch_offset_samples is None else 500+result.fractional_epoch_offset_samples-TRUE_EPOCH,
                carrier_error_hz=None if result.fractional_tracking_cfo_hz is None else result.fractional_tracking_cfo_hz-case['carrier_hz'])
        except Exception as error:
            row.update(error_type=type(error).__name__,error=str(error),scorer_elapsed_seconds=time.monotonic()-started)
        save(HERE/f'case-{index:02d}.json',row);outcomes.append(row)
    assert candidate_scores<=66
    save(HERE/'results.json',dict(outcomes=outcomes,component_tests=tests.testsRun,refine_calls=len(outcomes),candidate_glrt_scores=candidate_scores,
        elapsed_seconds=time.monotonic()-begun,protocol_sha256=digest(HERE/'protocol.json'),
        interpretation='Controlledcurrentalgorithm behavior only; nohistoricaldetectorbytes, noisy/multisourceacquisition,physicalclock orDSXcause inference'))
    print(json.dumps(dict(refine_calls=len(outcomes),candidate_glrt_scores=candidate_scores,elapsed_seconds=time.monotonic()-begun,
        outcomes=[{k:r.get(k) for k in ['name','estimated_epoch_samples','epoch_error_samples','carrier_error_hz','error']} for r in outcomes])),flush=True)


if __name__=='__main__':run()
