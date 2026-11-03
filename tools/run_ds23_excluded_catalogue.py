"""24-worker, per-scan calibration → catalogue search → joint association."""

from concurrent.futures import ProcessPoolExecutor, as_completed
import time

from calibrate_ds23_excluded_catalogue import OUT, run as calibrate
from screen_ds23_excluded_catalogue import run as screen
from fit_ds23_excluded_catalogue import prepare, run as fit
from run_algo01_ds23_sample import read, write


def job(case):
    rows = []
    for stage, function in (('calibrate', calibrate), ('screen', screen), ('fit', fit)):
        try:
            rows.append(dict(stage=stage, result=function(case)))
        except Exception as exc:
            raise RuntimeError(f'{case} {stage}: {exc!r}') from exc
    return dict(case=case, stages=rows)


def main():
    protocol = prepare()
    verification = read(OUT/'pilot_verification.json')
    if not verification['all_terminal'] or not verification['qualified']:
        raise ValueError('pilot RF replay must qualify before the complete cohort')
    began = time.monotonic()
    cases = protocol['development_cases']+protocol['confirmation_cases']
    receipts = []
    with ProcessPoolExecutor(max_workers=24) as pool:
        futures = {pool.submit(job, c):c for c in cases}
        for future in as_completed(futures):
            try:
                receipts.append(future.result())
            except Exception as exc:
                receipts.append(dict(case=futures[future], error=repr(exc)))
            write(OUT/'cohort_progress.json', dict(completed=len(receipts), total=len(cases), receipts=receipts))
    write(OUT/'cohort_execution.json', dict(all_terminal=True, receipts=receipts,
        errors=[r for r in receipts if 'error' in r], seconds=time.monotonic()-began))
    print('Terminal', len(receipts), 'errors', sum('error' in r for r in receipts), flush=True)


if __name__ == '__main__':
    main()
