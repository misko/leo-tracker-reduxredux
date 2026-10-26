"""One unchanged replay with observation-only coarse acquisition tracing."""
import dataclasses
import signal
import time
import numpy as np
from study import HERE, read, sha, dump, opened, analytic, injection, replay, EPOCH, CFO


def run():
    from leo.analysis.starlink import acquisition as acquisition
    from leo.scanner import fast_scan_detector
    from leo.scanner.fast_scan_analysis import production_glrt
    start=time.monotonic()
    def timeout(*_):
        raise TimeoutError('580-second single diagnostic replay limit')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(580)
    slot=read(HERE/'panel.json')['slots'][-1]
    window, ids, background, receipt=opened(slot)
    wave=analytic(len(background),window.sample_rate_hz,window.target['edge'])
    injected=np.column_stack([injection(background[:,i],wave,-24)[0] for i in range(len(ids))])
    changed=dataclasses.replace(window,samples=np.stack((injected.real,injected.imag),axis=-1))
    traces=[];acquired=[]
    original_retain=acquisition._retain_score_map_peaks
    original_acquire=fast_scan_detector.acquire_symbolwise
    def trace_retain(residuals, score_rows, count, epoch_sep, cfo_sep, epoch_count):
        retained=original_retain(residuals,score_rows,count,epoch_sep,cfo_sep,epoch_count)
        extended=original_retain(residuals,score_rows,256,epoch_sep,cfo_sep,epoch_count)
        def is_truth(item):
            score,epoch,cfo=item
            delta=(epoch-EPOCH+epoch_count/2)%epoch_count-epoch_count/2
            return abs(delta)<=5 and abs(cfo-CFO)<=80000
        local=[]
        for residual,scores in zip(residuals,score_rows,strict=True):
            for epoch in acquisition._local_peak_indexes(scores):
                local.append((float(scores[epoch]),int(epoch),float(residual)))
        truth=[item for item in local if is_truth(item)]
        best=max(truth,default=None)
        traces.append(dict(coarse_CFO_grid=list(residuals),timing_cells=epoch_count,
            original_count=count,original_NMS=retained,diagnostic_top256_NMS=extended,
            truth_in_original8=[dict(rank=i,score=x[0],epoch=x[1],cfo=x[2]) for i,x in enumerate(retained) if is_truth(x)],
            truth_in_top256=[dict(rank=i,score=x[0],epoch=x[1],cfo=x[2]) for i,x in enumerate(extended) if is_truth(x)],
            total_local_peaks=len(local),best_truth_neighborhood_local_peak=best,
            best_truth_local_peak_unconstrained_score_rank=1+sum(x[0]>best[0] for x in local) if best else None))
        return retained
    def trace_acquire(*args,**kwargs):
        result=original_acquire(*args,**kwargs)
        acquired.append(dict(receiver=kwargs.get('calibration',args[2] if len(args)>2 else None).receiver_id,
            config=dataclasses.asdict(kwargs['config']),result=dataclasses.asdict(result)))
        return result
    acquisition._retain_score_map_peaks=trace_retain
    fast_scan_detector.acquire_symbolwise=trace_acquire
    try:
        result=production_glrt(changed,ids)
    finally:
        acquisition._retain_score_map_peaks=original_retain
        fast_scan_detector.acquire_symbolwise=original_acquire
    actual=replay.exported(result)
    prior=next(r for r in read(HERE/'results.json')['rows'] if r['request_id']==slot['request_id'])
    old=next(o for o in prior['outcomes'] if o['rows'][0]['label']=='recorded' and o['rows'][0]['strength_db']==-24)
    comparisons={str(r['native_receiver_id']):replay.compare(
        [{k:v for k,v in c.items() if k not in ['timing_error_samples','cfo_error_hz']} for c in r['candidates']],
        actual[r['native_receiver_id']]) for r in old['rows']}
    dump(HERE/'diagnostic.json',dict(request_id=slot['request_id'],strength_db=-24,
        diagnostic_protocol_sha256=sha(HERE/'diagnostic_protocol.json'),physical_replays=1,
        historical_parity=receipt,primary_injection_export_parity=comparisons,
        all_export_parity_passed=all(c['all_passed'] for c in comparisons.values()),
        trace=traces,acquisition_calls=acquired,full_production_candidates=[r.model_dump(mode='json') for r in result],
        seconds=time.monotonic()-start,production_runtime_identity_unchanged=replay.runtime_identity()==read(HERE/'protocol.json')['identity']))
    signal.alarm(0)
    print('diagnostic complete',time.monotonic()-start,flush=True)


if __name__=='__main__':
    import sys
    if sys.argv[1]=='freeze':
        if (HERE/'diagnostic_protocol.json').exists():
            raise FileExistsError('diagnostic already frozen')
        dump(HERE/'diagnostic_protocol.json',dict(frozen_utc_ns=time.time_ns(),
            files={str(HERE/name):sha(HERE/name) for name in ['DIAGNOSTIC_PROTOCOL.md','diagnostic.py','panel.json','protocol.json','results.json']},
            physical_replays=1,maximum_seconds=580))
    else:
        for p,h in read(HERE/'diagnostic_protocol.json')['files'].items():
            if sha(p)!=h:raise ValueError('diagnostic frozen file changed: '+p)
        run()
