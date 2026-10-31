"""Fixed-epoch same-symbol continuous GLRT; seal measurement before residuals."""
import hashlib
import json
import signal
import time
from pathlib import Path
import numpy as np
from leo.analysis.starlink.fast_scan_scores import conditioned_glrt64_score
from leo.analysis.starlink.glrt_refinement_prototype import continuous_glrt_score

OUT=Path(__file__).resolve().parent


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('60s scorer cap')));signal.alarm(60)
    plan=json.loads((OUT/'raw-plan.json').read_text());bound=json.loads((OUT/'raw-pilot-receipt.json').read_text());export=json.loads((OUT/'raw-export-receipt.json').read_text())
    assert export['status']=='complete'
    bindings={r['visit_index']:r for r in bound['rows']};arrays={r['visit_index']:r for r in export['rows']}
    result=dict(status='running',seed=plan['seed'],same_epoch_symbols_64_and_alias=True,FFT_size=512,
        exact_control_both_refined=True,no_GPS_TLE_or_orbit_inputs=True,position_refit=False,rows=[],
        plan_sha256=sha(OUT/'raw-plan.json'),export_receipt_sha256=sha(OUT/'raw-export-receipt.json'),
        source_sha256={str(p):sha(p) for p in [Path(__file__),Path(conditioned_glrt64_score.__code__.co_filename),Path(continuous_glrt_score.__code__.co_filename)]})
    def save():
        result['seconds']=time.monotonic()-began;(OUT/'raw-pilot-measurements.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    samples={}
    # Exact replay of every frozen measurement precedes any continuous fit.
    for point in plan['points']:
        visit=point['visit_index'];b=bindings[visit];a=arrays[visit];assert sha(a['array'])==a['array_sha256']
        raw=np.load(a['array'],allow_pickle=False);y=raw[:,0].astype(float)+1j*raw[:,1].astype(float);samples[visit]=y
        replay=conditioned_glrt64_score(y,plan['sample_rate_hz'],epoch_sample=b['anchor'],acquired_cfo_hz=b['acquired_cfo_hz'],
            edge=point['edge'],glrt_size=512,fractional_epoch_offset_samples=b['fractional_offset_samples'])
        check=dict(CFO_difference_hz=replay.tracking_cfo_hz-b['fractional_tracking_cfo_hz'],
            exact_score_difference=replay.exact_score-b['exact_score'],control_score_difference=replay.control_score-b['control_score'])
        passed=abs(check['CFO_difference_hz'])<=1e-5 and max(abs(check['exact_score_difference']),abs(check['control_score_difference']))<=1e-7
        result['rows'].append(dict(kind=point['kind'],observation_id=point['observation_id'],visit_index=visit,
            archived_CFO_hz=b['fractional_tracking_cfo_hz'],conditioning_CFO_hz=b['acquired_cfo_hz'],
            original_fractional_epoch_samples=b['fractional_offset_samples'],original_anchor=b['anchor'],
            archived_exact_score=b['exact_score'],archived_control_score=b['control_score'],archived_margin=b['exact_score']-b['control_score'],
            discrete_replay=check,discrete_replay_passed=passed))
    result['all_discrete_replays_passed']=all(r['discrete_replay_passed'] for r in result['rows']);save()
    if not result['all_discrete_replays_passed']:
        result['status']='blocked_discrete_replay';save();return
    for point,row in zip(plan['points'],result['rows'],strict=True):
        b=bindings[point['visit_index']]
        score,detail=continuous_glrt_score(samples[point['visit_index']],plan['sample_rate_hz'],anchor=b['anchor'],offset=b['fractional_offset_samples'],
            conditioning_cfo_hz=b['acquired_cfo_hz'],edge=point['edge'])
        period=1/4.4e-6;delta=(score.tracking_cfo_hz-b['fractional_tracking_cfo_hz']+period/2)%period-period/2
        row.update(continuous_CFO_hz=b['fractional_tracking_cfo_hz']+delta,subbin_CFO_delta_hz=delta,
            continuous_exact_score=score.exact_score,continuous_control_score=score.control_score,
            continuous_margin=score.margin,continuous_peaks=detail,same_alias=True)
        assert abs(delta)<period/2
    result['status']='complete';save()
    seal=dict(measurement_sha256=sha(OUT/'raw-pilot-measurements.json'),sealed_before_orbital_residual_read=True,
        measurement_plan_sha256=sha(OUT/'raw-plan.json'),measurement_only=True)
    (OUT/'raw-pilot-measurement-seal.json').write_text(json.dumps(seal,indent=2)+'\n')
    print('measurement complete',len(result['rows']),'seconds',result['seconds'],flush=True)


if __name__=='__main__':main()
