"""Reporting must not turn pending or unconverged fits into model wins."""
from build_report import evidence_summary, table


def test_report_separates_saved_from_converged_and_qualifies_pairs():
    rows=[dict(scan='a',status='complete',converged=True,boundary=False),
          dict(scan='b',status='complete',converged=False,boundary=False),
          dict(scan='c',status='pending',converged=None,boundary=None)]
    base=dict(contrast='model',held_fixed='original',both_converged=True,either_boundary=False)
    pairs=[dict(base,scan='a',change_m=-100),
           dict(base,scan='b',change_m=-9000,both_converged=False),
           dict(base,scan='c',change_m=-8000,either_boundary=True)]
    result=evidence_summary(rows,pairs)
    assert (result['saved'],result['converged'],result['planned'])==(2,1,3)
    assert result['complete_scans']==[]
    effect=result['effects'][0]
    assert effect['available']==3 and effect['qualified']==1
    assert effect['median_change_m']==-100 and effect['scans']==['a']


def test_empty_report_evidence_has_no_invented_winners():
    assert evidence_summary([],[])['effects']==[]
    assert '\\|' in table(['header'],[['x|y']])
