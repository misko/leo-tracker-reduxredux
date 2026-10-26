"""Independent counts/information boundaries on the frozen control receipt."""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def test_primary_frequency_screen_has_real_innovation_not_tripled_trials():
    x=json.loads((HERE/'control_audit.json').read_text())
    p=x['signal']['-12/well_timed']['quadratic_or_fallback']
    assert p['independent_targets']==p['admitted_within500']==48
    assert p['before_mean_absolute_error_hz']>1000 and p['after_mean_absolute_error_hz']<200
    assert p['zero_innovations']==5
    assert x['primary_practical_RF_screen_passed']
    assert not x['uncertainty_calibrated'] and not x['full_dataset_promotion']


def test_null_exposure_is_per_independent_stratum():
    x=json.loads((HERE/'control_audit.json').read_text())
    assert len(x['null'])==4
    for row in x['null'].values():
        primary=row['quadratic_or_fallback/admitted']
        assert primary['n']==32 and primary['count']==0 and primary['upper95']>.08
