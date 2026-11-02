"""Bounded no-fit numerical reconstruction preflight, one lexical case/cohort."""
from pathlib import Path
import signal
import time
import numpy as np
from algo07_science import engine as e
from algo07_science.diagnose import objective
from evidence import native_inventory
import run as driver


def main():
    roster=driver.read(driver.ROOT/'rf_roster.json')
    representatives=[next(r for r in roster['cases'] if r['dataset']==ds)
                     for ds in sorted({r['dataset'] for r in roster['cases']})]
    rows=[];began=time.monotonic();signal.signal(signal.SIGALRM,driver.timeout)
    for row in representatives:
        tic=time.monotonic();signal.setitimer(signal.ITIMER_REAL,30.)
        try:
            path=Path(row['input_path']);assert driver.sha(path)==row['input_sha256']
            e.configure(path.parent.parent,driver.ROOT/'preflight_engine')
            e.ROOTS[row['case'][:4]]=path.parent.parent
            d,z,replay=e.load_case(row['case']);arms={}
            for arm,(p,x) in d['problems'].items():
                inv=native_inventory(p,d);difference=objective(p,d,x)-row['baseline'][arm]['objective']
                assert abs(difference)<1e-4
                assert inv['owners']==z['baseline_owners'][arm]
                arms[arm]=dict(objective_replay_difference=difference,native_counts=inv['counts'],
                               native_ids_sha256=inv['native_ids_sha256'],
                               numerical_diagnostics=driver.numerical.baseline_diagnostic(d,arm))
            rows.append(dict(case=row['case'],status='passed',arms=arms,seconds=time.monotonic()-tic))
        except Exception as exc:rows.append(dict(case=row['case'],status='failed',reason=repr(exc),seconds=time.monotonic()-tic))
        finally:signal.setitimer(signal.ITIMER_REAL,0.)
    receipt=dict(no_new_fit=True,no_truth_used=True,seconds=time.monotonic()-began,rows=rows)
    driver.write(driver.ROOT/'preflight.json',receipt)
    print([(r['case'],r['status'],round(r['seconds'],2)) for r in rows],flush=True)


if __name__=='__main__':main()
