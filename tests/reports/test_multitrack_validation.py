"""Independent rejection tests for paired real-data multitrack support."""
import csv
import copy
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]/'reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay/single-track/multitrack'
spec=importlib.util.spec_from_file_location('multitrack_validation',ROOT/'validate_real.py')
V=importlib.util.module_from_spec(spec);spec.loader.exec_module(V)

def observations():
    return list(csv.DictReader((ROOT/'data/observations.csv').open()))

def test_real_support_counts_and_split():
    result=V.audit_rows(observations())
    assert len(result)==8
    assert sum(r['training_rows'] for r in result)==64
    assert sum(r['held_rows'] for r in result)==208

@pytest.mark.parametrize('field,value',[('device_counter','0'),('common_rx1_minus_rx0_authority_hz','0'),('phase_rad','nan'),('split','evaluation')])
def test_misalignment_independent_correction_and_invalid_samples_rejected(field,value):
    rows=copy.deepcopy(observations());rows[0][field]=value
    with pytest.raises(AssertionError):V.audit_rows(rows)
