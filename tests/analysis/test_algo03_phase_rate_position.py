import pytest
from probe_algo03_phase_rate_position import previous_lines


def test_previous_catalogue_supports_alpha5_and_validates_pairs():
    assert previous_lines("name\n1 A0003 rest\n2 A0003 rest")=={100003:("1 A0003 rest","2 A0003 rest")}
    with pytest.raises(ValueError,match="identity"):
        previous_lines("1 12345 rest\n2 54321 rest")
    with pytest.raises(ValueError,match="unique"):
        previous_lines("1 12345 rest\n2 12345 rest\n1 12345 rest\n2 12345 rest")
