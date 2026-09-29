import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('window_cfo', Path(__file__).with_name('analyze.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def probe(rx, window, frequencies):
    return {'receiver_id': rx, 'probe_index': window,
            'candidates': [{'tracking_cfo_hz': f, 'passed_margin_gate': True} for f in frequencies]}


def test_receiver_separation_and_missing_history():
    assert module.differences([probe(0,0,[10]), probe(1,1,[10])],1) == ([],1,1)


def test_large_jumps_and_duplicate_entries_stay_in_denominator():
    assert module.differences([probe(0,0,[0]),probe(0,1,[200000,200000])],1) == ([200000,200000],2,0)


def test_requested_gap_and_nearest_bank():
    p = [probe(0,0,[100,200]),probe(0,1,[1000]),probe(0,2,[201])]
    assert module.differences(p,2) == ([1],1,0)
