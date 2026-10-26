"""Audit frequency information versus a donor-centered 512-bin quantizer."""

import collections
import gzip
import json
import math
from pathlib import Path

from baseline_scope import sha

HERE=Path(__file__).resolve().parent
TIMING=HERE.parent/'timing'
BIN=10000000/(44*512)


def read(path):
    with (gzip.open(path,'rt') if str(path).endswith('.gz') else Path(path).open()) as stream:return json.load(stream)


def summarize(rows):
    n=len(rows)
    if not n:return dict(n=0)
    donor=[r['donor_error_hz'] for r in rows];mean=sum(donor)/n
    errors=[r['after_error_hz'] for r in rows]
    denom=sum((d-mean)**2 for d in donor)
    slope=sum((d-mean)*e for d,e in zip(donor,errors))/denom if denom else None
    return dict(n=n,before_mean_absolute_error_hz=sum(abs(r['before_error_hz']) for r in rows)/n,
        after_mean_absolute_error_hz=sum(abs(r['after_error_hz']) for r in rows)/n,
        zero_residual_bins=sum(r['zero_bin'] for r in rows),
        after_error_regression_slope_on_donor_error=slope,
        mean_frequency_update_hz=sum(r['frequency_update_hz'] for r in rows)/n)


def main():
    signal=read(TIMING/'outcomes/signal.json.gz');rows=[]
    for trial in signal['rows']:
        if trial['db']!=-12:continue
        result=trial['result'];item=result['search'];mode=result['mode_provenance'][item['selected']['mode_index']]
        c=item['confirmation'];truth=213456.75+trial['true_rate_hz_s']*(.354+.01)
        assert abs(c['tracking_cfo_hz']-(mode['cfo_hz']+c['residual_cfo_hz']))<1e-8
        rows.append(dict(forecast=trial['forecast'],true_rate_hz_s=trial['true_rate_hz_s'],
            donor_error_hz=trial['donor_error_hz'],timing_offset_samples=trial['timing_offset_samples'],
            before_error_hz=mode['cfo_hz']-truth,after_error_hz=c['tracking_cfo_hz']-truth,
            zero_bin=c['residual_cfo_hz']==0.,frequency_update_hz=c['residual_cfo_hz']))
    stratified={f'{f}/rate{rate:g}/donor{error:g}':summarize([r for r in rows
        if (r['forecast'],r['true_rate_hz_s'],r['donor_error_hz'])==(f,rate,error)])
        for f in ('zero_rate_fallback','rate_propagated') for rate in (-2000.,2000.) for error in (-200.,200.)}
    natural=[];case_summaries={};source={str(TIMING/'outcomes/signal.json.gz'):sha(TIMING/'outcomes/signal.json.gz')}
    for path in sorted(HERE.glob('DS24-*_additions.json')):
        ledger=read(path);case=ledger['case'];source[str(path)]=sha(path)
        targets={a['target_observation_id']:a for a in ledger['staged']}
        raw_path=TIMING/'outcomes'/(case+'.json.gz');source[str(raw_path)]=sha(raw_path)
        owner_to_target={a['prediction_id']:a for a in targets.values()}
        local=[]
        for window in read(raw_path)['rows']:
            for cell in window['cells']:
                if cell['prediction_id'] not in owner_to_target:continue
                a=owner_to_target[cell['prediction_id']];r=cell['result'];i=r['search'];c=i['confirmation']
                mode=r['mode_provenance'][i['selected']['mode_index']]
                assert abs(c['tracking_cfo_hz']-mode['cfo_hz']-c['residual_cfo_hz'])<1e-8
                row=dict(case=case,target_observation_id=a['target_observation_id'],channel=a['channel'],
                    receiver=a['receiver'],predicted_CFO_hz=mode['cfo_hz'],measured_CFO_hz=c['tracking_cfo_hz'],
                    residual_bin_hz=c['residual_cfo_hz'],zero_bin=c['residual_cfo_hz']==0.,
                    earlier_width_hz=mode['cfo_half_width_hz'],donor_count=len(mode['donors']),
                    same_donor_origin_reused_as_scalar=c['residual_cfo_hz']==0.,
                    raw_target_support_is_new=True,independent_scalar_frequency_claim=False)
                local.append(row);natural.append(row)
        case_summaries[case]=dict(new_native=len(local),zero_residual_bin=sum(r['zero_bin'] for r in local),
            updated_residual_bin=sum(not r['zero_bin'] for r in local))
    out=dict(schema='missed-visit-frequency-information-audit-v1',FFT_bin_spacing_hz=BIN,
        idealized_uniform_bin_sigma_hz=BIN/math.sqrt(12),
        uniform_bin_sigma_is_calibrated=False,
        strong_all=summarize(rows),strong_by_forecast={f:summarize([r for r in rows if r['forecast']==f])
            for f in ('zero_rate_fallback','rate_propagated')},strong_strata=stratified,strong_rows=rows,
        natural_cases=case_summaries,natural_new_native=len(natural),natural_zero_bins=sum(r['zero_bin'] for r in natural),
        natural_rows=natural,source_hashes=source,
        limitation='A later FFT supports a conditional frequency bin whose origin depends on donors. Zero-bin output numerically equals its earlier prediction. Native sample disjointness does not establish independent scalar frequency errors or precision below the bin.',
        position_requirement='Explain donor-origin quantization dependence and measurement weight. Existing radio-noise proxy may be below an idealized bin scale; graph exploration remains useful but does not qualify independent precise Doppler factors.',
        no_scorer_or_parameters_changed=True,no_geography_read=True)
    # New snapshots are versioned by processed-case count; no prior audit is overwritten.
    name=f'frequency_information_{len(case_summaries):02d}cases.json'
    with (HERE/name).open('x') as stream:
        json.dump(out,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({k:out[k] for k in ('FFT_bin_spacing_hz','idealized_uniform_bin_sigma_hz',
        'strong_by_forecast','natural_cases','natural_new_native','natural_zero_bins')},indent=2))


if __name__=='__main__':main()
