"""A signed forecast uses only causal TLE innovations, age and epoch gap."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from probe_ds23_causal_phase_mean import forecast_phase_mean


def test_missing_history_or_near_duplicate_epoch_cannot_create_a_forecast():
    rows=[dict(old_new_alignment_s=None,previous_epoch_gap_s=None,age_s=1000,sigma_s=1),
          dict(old_new_alignment_s=5,previous_epoch_gap_s=.001,age_s=1000,sigma_s=1)]
    assert forecast_phase_mean(rows,1).tolist()==[0,0]


def test_forecast_sign_budget_and_zero_control():
    rows=[dict(old_new_alignment_s=2,previous_epoch_gap_s=1000,age_s=850,sigma_s=3),
          dict(old_new_alignment_s=-100,previous_epoch_gap_s=100,age_s=10000,sigma_s=1)]
    assert forecast_phase_mean(rows,.5).tolist()==pytest.approx([-1,3])
    assert forecast_phase_mean(rows,0).tolist()==[0,0]
