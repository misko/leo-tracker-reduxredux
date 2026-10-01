from summarize_full_pairs import compare


def row(accepted,error=None,runtime=10):
    return dict(accepted=accepted,error_m=error,runtime_s=runtime)


def test_pending_failures_and_matched_tolerance_remain_distinct():
    values=[
        dict(baseline=row(True,100),variant=row(True,100.5)),
        dict(baseline=row(True,1000),variant=row(True,100)),
        dict(baseline=row(False),variant=row(True,500)),
        dict(baseline=row(True,200),variant=row(False,runtime=175)),
        dict(baseline=row(False),variant=row(False)),
        dict(baseline=row(True,300),variant=None)]
    result=compare(values,'baseline')
    assert (result['planned'],result['audited'],result['pending'])==(6,5,1)
    assert (result['both_accepted'],result['improved'],result['within_one_metre'])==(2,1,1)
    assert result['target_only_accepted']==result['source_only_accepted']==result['neither_accepted']==1
    stats=result['variant_on_audited']
    assert stats['planned']==5 and stats['accepted']==3 and stats['failed']==2
    assert stats['runtime_s']['maximum']==175 and stats['within1000m']==3
