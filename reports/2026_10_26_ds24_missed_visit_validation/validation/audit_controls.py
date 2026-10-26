"""Independent fixed-point full-window controls/reference audit; no new scoring."""
import collections
import gzip
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
TIMING=HERE.parent/'timing'
R01=Path('/srv/bulk/leo/research/ds24-missed-visit-r01/validation')
sys.path.insert(0,str(R01))
from integration import upper95

BIN=10000000/(44*512)
METHODS=('linear','quadratic_or_fallback','legacy_adapter_linear')


def read(path):
    with (gzip.open(path,'rt') if str(path).endswith('.gz') else Path(path).open()) as stream:return json.load(stream)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    protocol=read(TIMING/'protocol.json')
    for path,digest in protocol['files'].items():assert sha(path)==digest,path
    approval=read(TIMING/'run_authorization.json');assert approval['protocol_sha256']==sha(TIMING/'protocol.json')
    documents={name:read(TIMING/'outcomes'/(name+'.json.gz')) for name in ('signal','null','wrong')}
    for name,doc in documents.items():
        assert doc['protocol_sha256']==sha(TIMING/'protocol.json')
        assert len({r['target_sha256'] for r in doc['rows']})==len(doc['rows'])
        for row in doc['rows']:
            result=row['result'];assert result['primary_operational_method']=='quadratic_or_fallback'
            assert not result['target_timing_or_mode_search']
            for method,item in result['methods'].items():
                point=item['point'];score=item['score']
                assert point['reference_offset_s']==.01
                if score['status']!='complete':continue
                innovation=score['tracking_cfo_hz']-point['cfo_hz']
                assert abs(innovation-item['frequency_innovation_hz'])<1e-8
                assert abs(innovation/BIN-round(innovation/BIN))<1e-8
                pilot=score['margin']>=.025;compatible=abs(innovation)<=point['cfo_half_width_hz']
                assert item['pilot_confirmed']==pilot and item['admitted']==(pilot and compatible)
                if name=='signal':
                    refs=row['reference_metadata']
                    assert (refs['target_reference_counter']-refs['earlier_reference_counter'])/10000000==.354
                    expected=213456.75+row['true_rate_hz_s']*.354
                    assert row['truth_CFO_midpoint_hz']==expected
                    assert abs(point['cfo_hz']-expected-row['donor_CFO_error_hz'])<1e-8
                    assert abs(row['evaluation'][method]['cfo_error_hz']-(score['tracking_cfo_hz']-expected))<1e-8
    signal=documents['signal']['rows'];summary={}
    for db in (-12,-24):
        for alignment in ('well_timed','stress'):
            selected=[r for r in signal if r['db']==db and (abs(r['timing_error_samples'])<=.5)==(alignment=='well_timed')]
            rows={}
            for method in METHODS:
                admitted=[r for r in selected if r['result']['methods'][method]['admitted']]
                errors=[r['evaluation'][method]['cfo_error_hz'] for r in selected]
                n=len(selected);accurate=sum(abs(r['evaluation'][method]['cfo_error_hz'])<=500 for r in admitted)
                rows[method]=dict(independent_targets=n,admitted=len(admitted),admitted_within500=accurate,
                    accurate500_all=sum(abs(e)<=500 for e in errors),
                    admitted_over1000=sum(abs(r['evaluation'][method]['cfo_error_hz'])>1000 for r in admitted),
                    before_mean_absolute_error_hz=sum(abs(r['donor_CFO_error_hz']) for r in selected)/n,
                    after_mean_absolute_error_hz=sum(abs(e) for e in errors)/n,
                    zero_innovations=sum(r['result']['methods'][method]['frequency_innovation_hz']==0 for r in selected),
                    screen_pass=n>=20 and accurate/n>=.9)
            summary[f'{db}/{alignment}']=rows
    all_strong=[r for r in signal if r['db']==-12]
    primary_bad=sum(r['result']['methods']['quadratic_or_fallback']['admitted'] and
        abs(r['evaluation']['quadratic_or_fallback']['cfo_error_hz'])>1000 for r in all_strong)
    null={}
    for edge in ('lower','upper'):
        for distinct in (False,True):
            rows=[r for r in documents['null']['rows'] if r['edge']==edge and r['distinct_method_points']==distinct]
            methods={}
            for method in (*METHODS,'union'):
                for kind in ('pilot_confirmed','admitted'):
                    k=sum(any(r['result']['methods'][m][kind] for m in METHODS) if method=='union'
                        else r['result']['methods'][method][kind] for r in rows)
                    bound=upper95(k,len(rows))
                    methods[f'{method}/{kind}']=dict(count=k,n=len(rows),upper95=bound,
                        practical_pass=len(rows)>=32 and k/len(rows)<=.05 and bound<=.10)
            null[f'{edge}/distinct{distinct}']=methods
    wrong={method:dict(n=len(documents['wrong']['rows']),pilot_confirmed=sum(r['result']['methods'][method]['pilot_confirmed'] for r in documents['wrong']['rows']),
        admitted=sum(r['result']['methods'][method]['admitted'] for r in documents['wrong']['rows'])) for method in METHODS}
    passed=summary['-12/well_timed']['quadratic_or_fallback']['screen_pass'] and primary_bad==0 and all(
        row['quadratic_or_fallback/admitted']['practical_pass'] for row in null.values())
    errors_by_origin={}
    for error in sorted({r['donor_CFO_error_hz'] for r in signal}):
        rows=[r for r in signal if r['db']==-12 and abs(r['timing_error_samples'])<=.5 and r['donor_CFO_error_hz']==error]
        errors_by_origin[str(error)]=dict(n=len(rows),before_absolute_error_hz=abs(error),
            after_mean_absolute_error_hz=sum(abs(r['evaluation']['quadratic_or_fallback']['cfo_error_hz']) for r in rows)/len(rows),
            zero_innovations=sum(r['result']['methods']['quadratic_or_fallback']['frequency_innovation_hz']==0 for r in rows))
    out=dict(schema='round2-independent-control-audit-v1',source_integrity_passed=True,signal=summary,
        null=null,wrong_pilot=wrong,primary_admitted_strong_errors_over1000=primary_bad,
        primary_practical_RF_screen_passed=passed,frequency_origin_strata=errors_by_origin,
        source_or_measurement_errors=[],uncertainty_calibrated=False,full_dataset_promotion=False,
        reference_review='Wave carrier and independently quadratic clock are centered at dt=t-.010; earlier and target midpoint gap is exactly.354s. All scorer methods use their epoch directly without extra timing advance.',
        no_new_RF_scoring=True,held_validation_target_outcomes_opened=False,geography_used=False,
        protocol_sha256=sha(TIMING/'protocol.json'),outcome_hashes={name:sha(TIMING/'outcomes'/(name+'.json.gz')) for name in documents})
    with (HERE/'control_audit.json').open('x') as stream:json.dump(out,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(dict(primary_pass=passed,strong_primary=summary['-12/well_timed']['quadratic_or_fallback'],
        strong_stress=summary['-12/stress']['quadratic_or_fallback'],primary_bad=primary_bad,
        null_primary={k:v['quadratic_or_fallback/admitted'] for k,v in null.items()},wrong=wrong),indent=2))


if __name__=='__main__':main()
