"""Finish reporting after the frozen full pass; does not run or alter fits."""
import time
import sys
import run_variants as run
# The reused engine prepends its own report directory for numerical helpers.
# Reporting modules here must win over older files with the same names.
sys.path.insert(0,str(run.HERE))


def main():
    while not (run.HERE/'results_full.json').exists():
        time.sleep(5.)
    completed=run.read(run.HERE/'results_full.json')
    assert len(completed['results'])==192
    failures=[r for r in completed['results'] if r.get('status')=='failed']
    assert not failures,failures
    import analyze
    result=analyze.gather()
    assert result['complete']
    analyze.export(result,partial=False)
    print('SUMMARY AND PLOTS COMPLETE',flush=True)
    import validate
    validate.validate(run.LABELS,'full')
    import status
    status.main()
    import report
    report.main()


if __name__=='__main__':main()
