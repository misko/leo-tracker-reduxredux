from curvature_threshold_sweep import screen,THRESHOLDS


def test_stricter_screen_is_nested_and_unassessed_is_explicit():
    tracks=[dict(catalog_number=1,ratio=1.075),dict(catalog_number=1,ratio=1.01),
            dict(catalog_number=2,ratio=1.04),dict(catalog_number=3,ratio=None)]
    previous={1,2,3,4}
    for threshold in THRESHOLDS:
        result=screen([1,2,3,4],tracks,threshold)
        assert set(result['kept'])<=previous
        assert result['unassessed']==[3,4]
        assert {3,4}<=set(result['kept'])
        previous=set(result['kept'])
    assert screen([1,2,3,4],tracks,1.075)['kept']==[1,2,3,4]
    assert screen([1,2,3,4],tracks,1.025)['kept']==[3,4]
