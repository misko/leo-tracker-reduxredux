from reports.ALGO08.v3.small_raw_residency import complete


def test_partial_or_unobservable_files_cannot_enroll_a_raw_pair():
    base = dict(members=3, observed_members=3, cached_pages=48, observed_file_pages=48, unavailable={})
    assert complete(base)
    for change in (dict(cached_pages=47), dict(observed_members=2), dict(members=0),
                   dict(unavailable={"EACCES": 1}), dict(cached_pages=None)):
        assert not complete(base | change)
