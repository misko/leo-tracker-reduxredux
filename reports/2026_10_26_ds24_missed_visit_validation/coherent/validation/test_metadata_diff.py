"""A metadata repair must not hide a numeric or ownership change."""
import pytest
from audit_metadata import check_label_diff


def test_only_integer_to_string_stream_labels_are_allowed():
    assert check_label_diff({'stream_generation':9,'CFO':1.5},{'stream_generation':'stream','CFO':1.5})==1
    with pytest.raises(AssertionError):check_label_diff({'stream_generation':9,'CFO':1.5},{'stream_generation':'stream','CFO':2.5})
    with pytest.raises(AssertionError):check_label_diff({'start_counter':9},{'start_counter':10})
