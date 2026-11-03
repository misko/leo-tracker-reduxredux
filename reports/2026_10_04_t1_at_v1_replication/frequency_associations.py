"""N01--N16 selection with a fixed Gaussian residual term, no changed input pool."""
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np
from regularized_associations import Search,compile_mode,INPUTS,OLD_INPUTS,SCANS,ARMS,HERE,LEGACY
from numeric_data import load
from timing_bound_comparison import digest
from subset_positions import serial
from frequency_selection_score import FrequencyPriorMixin

OUT=HERE/'frequency-regularized-selection'
PREVIOUS=HERE/'timing-regularized-selection'
MODE='frequency-regularized'


class FrequencySearch(FrequencyPriorMixin,Search):pass


def run(scan):
    meta=json.loads((OLD_INPUTS/scan/'input.json').read_text())
    old_path=Path(meta['association_source']);pool_path=old_path.with_name('candidate-pool.json')
    pool=json.loads(pool_path.read_text());data=load(INPUTS/scan/'seed-timing-v6')
    assert pool['original_rows']==data.original_rows.tolist()
    assert [(m['catalog_number'],m['offset_s']) for m in pool['arms'][ARMS[0]]]==[(m['catalog_number'],m['offset_s']) for m in pool['arms'][ARMS[1]]]
    folder=OUT/scan;folder.mkdir(parents=True,exist_ok=True)
    for arm in ARMS:
        target=folder/f'{arm}.json'
        if target.exists():continue
        modes=[compile_mode(m,data.receiver,data.channel) for m in pool['arms'][arm]]
        previous_path=PREVIOUS/scan/f'{arm}-timing-regularized.json'
        previous=json.loads(previous_path.read_text())
        # Full-cohort zero-weight control: ensure only the intended score changes.
        control=FrequencySearch(modes,data.group,data.times,frequency_weight=0.).run(3)
        result=FrequencySearch(modes,data.group,data.times,frequency_weight=1.).run(3)
        for r in (control,result):
            for stage in ('initial','final'):
                values=r[stage]
                for a in values['assignments']:a['row_index']=int(data.original_rows[a['row_index']])
                values.update(denominator=len(data.times),coverage=values['assigned']/len(data.times),unassigned=len(data.times)-values['assigned'])
        for stage in ('initial','final'):
            for key in ('assigned','satellites','objective','assignments','selected'):
                assert control[stage][key]==previous[stage][key],(scan,arm,stage,key)
        assert control['passes']==previous['passes']
        result.update(scope=__doc__,scan=scan,arm=arm,mode=MODE,frequency_weight=1.,timing_weight=1.,
            frequency_sigma_hz=200.,original_rows=data.original_rows,heldout_original_rows=[],
            zero_frequency_control_exact=True,previous_source_sha256=digest(previous_path),
            source_sha256=digest(pool_path),observations=data.sources,
            primary_score='assigned_windows - 10 * satellites - timing_prior - 0.5 * sum((residual_hz / 200)^2)',
            interpretation='Regularized coverage proxy, not the exact downstream finite-set likelihood.',
            implementation_sha256={str(p):digest(p) for p in (Path(__file__),HERE/'frequency_selection_score.py',HERE/'timing_selection_score.py',LEGACY/'penalty_replace_search.py')},
            rms_hz=float(np.sqrt(np.mean([a['residual_hz']**2 for a in result['final']['assignments']]))))
        target.write_text(json.dumps(result,default=serial,indent=2,allow_nan=False))
        print('FREQUENCY SELECTION',scan,arm,result['final']['assigned'],len(data.times),result['final']['satellites'],round(result['rms_hz'],1),flush=True)
    return scan


if __name__=='__main__':
    with ProcessPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(run,s) for s in SCANS]):print('SCAN COMPLETE',f.result(),flush=True)
