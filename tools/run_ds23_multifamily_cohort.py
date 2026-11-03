"""Bounded 24-worker orchestration after the RF-only pilot replay qualifies."""

from concurrent.futures import ProcessPoolExecutor, as_completed
import time

from probe_ds23_multifamily_proposals import OUT, prepare, run
from run_algo01_ds23_sample import read, write


def main():
    protocol = prepare()
    validation = read(OUT / 'verification_pilot.json')
    if not validation['all_terminal'] or not validation['qualified']:
        raise ValueError('RF pilot replay must qualify before the cohort run')
    cases = protocol['development_cases'] + protocol['confirmation_cases']
    receipts, began = [], time.monotonic()
    with ProcessPoolExecutor(max_workers=protocol['workers']) as pool:
        futures = {pool.submit(run, c): c for c in cases}
        for future in as_completed(futures):
            try:
                receipts.append(future.result())
            except Exception as exc:
                receipts.append(dict(case=futures[future], error=repr(exc)))
            write(OUT / 'cohort_progress.json', dict(completed=len(receipts), total=len(cases), receipts=receipts))
    for cohort in ('development', 'confirmation'):
        members = set(protocol[cohort + '_cases'])
        write(OUT / (cohort + '_execution.json'), dict(all_terminal=True,
            receipts=[r for r in receipts if r['case'] in members]))
    write(OUT / 'cohort_execution.json', dict(all_terminal=True, receipts=receipts,
        seconds=time.monotonic()-began, errors=[r for r in receipts if 'error' in r]))
    print('Terminal', len(receipts), 'errors', sum('error' in r for r in receipts), flush=True)


if __name__ == '__main__':
    main()
