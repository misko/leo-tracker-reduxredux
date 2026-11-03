import copy
import pytest
from audit_post_scan_tle import validate_element, HOUR_NS


def example():
    return dict(original=dict(line1='old1', line2='old2'),
                selected=dict(line1='new1', line2='new2', epoch_utc_ns=HOUR_NS, collected_utc_ns=2*HOUR_NS),
                post_scan=True, changed=True)


def test_post_epoch_and_collection_both_required():
    row = example(); validate_element(row, 0)
    for key, value in [('epoch_utc_ns', 0), ('epoch_utc_ns', 25*HOUR_NS), ('collected_utc_ns', 49*HOUR_NS)]:
        bad = copy.deepcopy(row); bad['selected'][key] = value
        with pytest.raises(AssertionError):validate_element(bad, 0)


def test_fallback_cannot_silently_change_orbit():
    row = example(); row['post_scan'] = False
    with pytest.raises(AssertionError):validate_element(row, 0)
    row['selected'].update(row['original']); row['changed'] = False
    validate_element(row, 0)
