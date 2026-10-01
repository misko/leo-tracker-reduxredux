from finalize_panel import statistics,matched


def test_failed_units_stay_in_threshold_denominators_and_runtime():
    rows=[dict(accepted=True,error_m=1000.,runtime_s=10.),dict(accepted=False,error_m=None,runtime_s=90.)]
    result=statistics(rows)
    assert result['planned']==2 and result['accepted']==1 and result['failed']==1
    assert result['within1000m']==1 and result['median_error_m']==1000.
    assert result['runtime_s']['median']==50. and result['runtime_s']['known']==2


def test_matched_comparison_keeps_asymmetric_failures_separate():
    rows=[]
    for block,accepted in [('A',[True,False,True]),('B',[False,True,True])]:
        for suffix,ok,error in zip(['S1','D1','Q'],accepted,[2000.,1500.,1000.]):
            rows.append(dict(unit=block+'-'+suffix,accepted=ok,error_m=error if ok else None))
    comparisons=matched(rows,['A','B'])
    q=comparisons['S1_to_Q']
    assert q['planned']==2 and q['both_accepted']==1 and q['target_only_accepted']==1
    assert q['improved']==1 and q['median_change_m']==-1000.
    pair=comparisons['S1_to_D1']
    assert pair['both_accepted']==0 and pair['median_change_m'] is None
    assert pair['target_only_accepted']==1 and pair['source_only_accepted']==1
