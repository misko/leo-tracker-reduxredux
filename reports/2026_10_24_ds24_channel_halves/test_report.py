from report import common_cases,error_km,REFERENCE


def test_comparison_requires_all_three_groups_for_same_scan():
    rows=[dict(case='a',group=g,error_km=1) for g in ('all_channels','ch1_4','ch5_8')]
    rows += [dict(case='b',group=g,error_km=None if g=='ch5_8' else 1) for g in ('all_channels','ch1_4','ch5_8')]
    assert common_cases(rows)=={'a'}
    assert error_km(REFERENCE)==0
