"""Replay the frozen worker without requiring earlier experimental caches."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from probe_ds23_causal_phase_location import run_case
from run_algo01_ds23_sample import ROOT, read, write

HERE = Path(__file__).resolve().parent


def job(case, output):
    result = run_case(case, str(output))
    result['path'] = str(output/(case+'.json'))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=20)
    parser.add_argument('--case', help='Single-record smoke replay; no population evaluation')
    args = parser.parse_args()
    protocol = read(HERE/'protocol.json')
    if args.case and args.case not in protocol['cases']:
        parser.error('case is outside the published matched population')
    if args.workers < 1 or args.workers > 20:
        parser.error('workers must be between 1 and 20')
    output = args.output_directory.resolve()
    if output.exists():
        parser.error('use a new output directory to preserve prior scientific results')
    output.mkdir(parents=True)
    protocol = dict(protocol, cache={}, replay_without_earlier_trial_caches=True,
                    single_case_smoke_only=args.case is not None)
    write(output/'protocol.json', protocol)
    cases = [args.case] if args.case else protocol['cases']
    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(job, case, output):case for case in cases}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(dict(case=futures[future], error=repr(exc)))
            write(output/'progress.json', dict(completed=len(results), total=len(cases), results=results))
    write(output/'execution.json', dict(results=results, all_terminal=True))
    if not args.case:
        import evaluate_ds23_causal_phase_location_full as reporter
        reporter.OUT = output
        reporter.main()


if __name__ == '__main__':
    main()
