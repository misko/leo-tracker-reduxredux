from audit_regularized_selection import selection_changes


def test_changes_separate_coverage_identity_and_timing():
    a={'final':dict(selected=[dict(catalog_number=1,offset_s=0.,count=2),dict(catalog_number=2,offset_s=3.,count=1)],
        assignments=[dict(row_index=10,catalog_number=1),dict(row_index=11,catalog_number=1),dict(row_index=12,catalog_number=2)])}
    b={'final':dict(selected=[dict(catalog_number=1,offset_s=1.,count=1),dict(catalog_number=3,offset_s=0.,count=2)],
        assignments=[dict(row_index=10,catalog_number=1),dict(row_index=11,catalog_number=3),dict(row_index=13,catalog_number=3)])}
    r=selection_changes(a,b)
    assert [x['catalog_number'] for x in r['removed']]==[2]
    assert [x['catalog_number'] for x in r['added']]==[3]
    assert [x['satellite'] for x in r['changed_timing']]==[1]
    assert (r['lost_windows'],r['gained_windows'],r['relabeled_windows'])==(1,1,1)
