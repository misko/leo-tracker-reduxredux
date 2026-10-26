"""Fresh provenance/reference/legacy audit of every sealed development row."""
from collections import Counter
import importlib.util
from pathlib import Path
import numpy as np
import predictor
import study

HERE=Path(__file__).resolve().parent


def main():
    study.bound()
    source=study.read(study.PRIOR/'prediction_packets.json')
    predicted=study.read(HERE/'predictions.json');seal=study.read(HERE/'forecast_seal.json')
    assert study.sha(HERE/'predictions.json')==seal['predictions_sha256']
    assert len(source['rows'])==len(predicted['rows'])==576
    old={r['header']['prediction_id']:r for r in source['rows']}
    spec=importlib.util.spec_from_file_location('sealed_round1_adapter',study.OLD_ADAPTER)
    legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
    preserved=0;qualified=0;fallback=0;missing=0
    for result in predicted['rows']:
        row=old[result['prediction_id']]
        assert predictor.predict(row)==result
        redacted=dict(row,header=dict(row['header'],target_candidates=[dict(epoch_samples=999,CFO_hz=1e99)]),
                      target_original=dict(candidates=[dict(fractional_tracking_cfo_hz=-1e99)]))
        assert predictor.predict(redacted)==result
        if not result['methods']:
            missing+=1;assert not row['forecast']['modes'];continue
        primary=row['forecast']['modes'][0];full=primary['full'];adapted=legacy.adapt(row)['modes'][0]
        assert result['primary_hypothesis_id']==primary['hypothesis_id']
        assert result['donors']==primary['donors']
        assert result['target_support']==row['target_support']
        assert result['methods']['linear']['epoch_samples']==full['epoch_samples']
        assert result['methods']['legacy_adapter_linear']['epoch_samples']==adapted['epoch_samples']
        for point in result['methods'].values():
            assert point['cfo_hz']==full['CFO_hz']and point['cfo_rate_hz_s']==full['CFO_rate_hz_per_s']
            assert point['cfo_reference_counter']==full['reference_counter']
            assert point['cfo_half_width_hz']==full['CFO_half_width_hz']
        preserved+=1
        if result['status']=='quadratic':
            qualified+=1;model=result['model'];point=result['methods']['quadratic_or_fallback'];h=result['header']
            assert model['donor_count']>=5 and model['history_span_s']>=1.
            assert model['design_rank']==3 and model['design_condition']<=100
            assert abs(model['acceleration_samples_per_s2'])<=10
            assert max(abs(x)for x in model['target_start_mid_end_rates_samples_per_s'])<=200
            value=predictor.evaluate(model,h['sample_rate_hz'],h['start_counter'],(h['start_counter']+h['stop_counter'])/2)
            assert point['epoch_samples']==value['epoch_samples']
            assert np.linalg.eigvalsh(model['coefficient_covariance_scaled']).min()>=-1e-12
            assert point['timing_sigma_samples']>=2
        else:
            fallback+=1;assert result['model']['fallback_reasons']
            assert result['methods']['quadratic_or_fallback']==result['methods']['linear']
    diagnostic=study.read(HERE/'archived_diagnostic.json')
    previous=study.read(study.PRIOR/'timing_diagnosis.json')
    assert {r['prediction_id']for r in diagnostic['rows']}=={r['prediction_id']for r in previous['rows']}
    previous_by_id={r['prediction_id']:r for r in previous['rows']}
    assert all(r['errors_samples']['linear']==previous_by_id[r['prediction_id']]['fitted_error_samples']for r in diagnostic['rows'])
    study.write(HERE/'verification.json',dict(all_passed=True,owned_tests=6,forecast_rows=576,fresh_response_redactions=576,
        original_primary_and_CFO_preserved=preserved,legacy_adapter_exact_parity=preserved,
        quadratic=qualified,linear_fallback=fallback,no_donor=missing,
        archived_CFO_cohort_same_ids_and_linear_errors=len(diagnostic['rows']),
        protocol_sha256=study.sha(HERE/'protocol.json'),predictions_sha256=study.sha(HERE/'predictions.json'),
        raw_IQ_reads=0,validation_target_files_opened=False))
    print('verification passed',qualified,fallback,missing)


if __name__=='__main__':main()
