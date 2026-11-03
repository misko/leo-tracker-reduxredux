from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from validate_ds23_synthetic_nuisance_components import balanced_sample


def members():
    return [dict(dataset_label=f'{fmt}-{k}',recording_format=fmt,error_km=k*100) for fmt in ('short_window_iq_recording','starlink_adaptive_hop_iq') for k in range(10)]


def test_balanced_sampling_ignores_errors_and_input_order():
    m=members();available={r['dataset_label'] for r in m}
    expected=balanced_sample(m,available,set(),3,57)
    for r in m:r['error_km']=-r['error_km']
    assert balanced_sample(list(reversed(m)),available,set(),3,57)==expected
    assert sum(c.startswith('short_window') for c in expected)==3
    assert sum(c.startswith('starlink_adaptive') for c in expected)==3


def test_missing_population_is_explicit():
    with pytest.raises(ValueError,match='insufficient'):
        balanced_sample(members(),set(),set(),3,57)
