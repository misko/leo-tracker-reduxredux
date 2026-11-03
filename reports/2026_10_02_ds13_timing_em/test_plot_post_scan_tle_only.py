import copy
import json
import pytest
from plot_post_scan_tle_only import SOURCE, select_genuine


def test_saved_comparison_has_three_genuine_post_scan_epochs():
    selected=select_genuine(json.loads(SOURCE.read_text()))
    assert [t['catalog_number'] for t,e in selected]==[68299,66186,58622]


def test_rejects_later_download_with_pre_scan_element_epoch():
    receipt=copy.deepcopy(json.loads(SOURCE.read_text()))
    scan=next(s for s in receipt['scans'] if s['scan']=='A')
    element=next(e for e in scan['elements'] if e['catalog_number']==68299)
    element['later']['epoch_utc_ns']=scan['origin_utc_ns']-1
    with pytest.raises(ValueError,match='epoch'):
        select_genuine(receipt)
