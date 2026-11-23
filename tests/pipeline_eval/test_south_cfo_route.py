from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'reports/ALGO08/v3'))

from south_cfo_route import CFO,admissible,audit_selected


def test_south_paging_cap_counts_in_both_authenticated_extents():
    payload = dict(members=19,observed_members=19,observed_file_pages=550,cached_pages=425,unavailable={})
    indexes = dict(payload,observed_file_pages=19,cached_pages=16)
    record = dict(payload=payload,indexes=indexes)
    assert not admissible(record)
    assert admissible(record,128)
    assert not admissible(record,127)
    indexes['unavailable'] = {'EPERM':1}
    assert not admissible(record,128)


def probes():
    data = [dict(visit_index=visit,receiver_id=radio,edge='lower',channel=1,actual_rf_hz=10.5e9,
                 candidates=[{'passed_fractional_margin_gate':True,CFO:45.5,'epoch':10}])
            for visit in range(2) for radio in range(2)]
    return dict(source=dict(probes=data),provenance=dict(processed_windows=2,window_count=2,invalid_capture=0))


def test_south_audit_requires_selected_support_original_full_anchors_and_fixed_epoch():
    original = probes()
    history = deepcopy(original)
    history['source']['probes'][3]['candidates'] = []
    actual = deepcopy(history)
    actual['source']['probes'][2]['candidates'][0][CFO] = 44.5
    measured = audit_selected(original,history,actual,{'route':'history'})
    assert measured['selected'] == 3 and measured['measured'] == 4
    assert measured['changed'] == [[1,0,45.5,44.5]]
    with pytest.raises(ValueError,match='chosen support'):
        audit_selected(original,history,actual,{'route':'unfiltered'})
    actual['source']['probes'][2]['candidates'][0]['epoch'] = 11
    with pytest.raises(ValueError,match='only fixed-epoch CFO'):
        audit_selected(original,history,actual,{'route':'history'})
    actual = deepcopy(history)
    actual['source']['probes'][1]['candidates'][0][CFO] = 44.5
    with pytest.raises(ValueError,match='full anchor CFO'):
        audit_selected(original,history,actual,{'route':'history'})
