import cProfile, json, pstats, time, sys
import os
from pathlib import Path
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from leo.scanner.adaptive_hop_analysis import analyze_adaptive_hop_visit, VariableDwellAnalysisConfigurationV5

sid=sys.argv[1] if len(sys.argv)>1 else 'scan-fw-aadec7177d989684'
output=Path('/var/tmp/glrt-profile-'+sid)
variant=os.environ.get('GLRT_VARIANT','baseline')
output=Path(str(output)+'-'+variant)
if variant == 'fft':
    from leo.analysis.starlink import acquisition
    from glrt_fft_trial import fft_grid
    acquisition._folded_anchor_score_grid=fft_grid
if variant == 'padded':
    import numpy as np
    from leo.analysis.starlink import acquisition as acquisition
    original=acquisition._folded_anchor_score_grid
    def padded(values,template,rate,frequencies,symbols,epochs):
        n=len(frequencies)
        if n>1 and n%4:
            step=frequencies[-1]-frequencies[-2]
            frequencies=(*frequencies,*(frequencies[-1]+step*i for i in range(1,5-n%4)))
        return original(values,template,rate,frequencies,symbols,epochs)[:n]
    acquisition._folded_anchor_score_grid=padded
if variant == 'tiled':
    from leo.analysis.starlink import acquisition
    original=acquisition._folded_anchor_score_grid
    def tiled(values,template,rate,frequencies,symbols,epochs):
        result=[]
        for start in range(0,len(frequencies),11):
            tile=frequencies[start:start+11]
            count=len(tile)
            if count<11:
                step=frequencies[1]-frequencies[0]
                tile=(*tile,*(tile[-1]+step*i for i in range(1,12-count)))
            result.extend(original(values,template,rate,tile,symbols,epochs)[:count])
        return tuple(result)
    acquisition._folded_anchor_score_grid=tiled
store=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True)
inputs=AdaptiveHopAnalysisInputStore(store)
prof=cProfile.Profile()
rows=[]
with inputs.source(sid) as source:
    cfg=VariableDwellAnalysisConfigurationV5(sample_rate_hz=source.receipt.plan.geometry.sample_rate_hz,receiver_ids=source.receipt.plan.geometry.receiver_ids,probe_stride_ms=120)
    for index in (0,71,503,1701):
        t=time.perf_counter(); cpu=time.process_time()
        result=prof.runcall(analyze_adaptive_hop_visit,source,index,configuration=cfg)
        rows.append(dict(index=index,seconds=time.perf_counter()-t,cpu_seconds=time.process_time()-cpu,product=result.model_dump(mode='json')))
output.with_suffix('.json').write_text(json.dumps(rows))
prof.dump_stats(str(output.with_suffix('.prof')))
pstats.Stats(prof).strip_dirs().sort_stats('cumulative').print_stats(25)
print('timings',[(r['index'],round(r['seconds'],3),round(r['cpu_seconds'],3)) for r in rows])
