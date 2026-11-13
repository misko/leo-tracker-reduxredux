"""Record bounded evaluation status every five minutes without launching work."""
import argparse
import json
import subprocess
import time
from pathlib import Path


def snapshot(unit, archive, expected):
    try:
        process = subprocess.run(
            ['systemctl', '--user', 'show', unit,
             '--property=LoadState,ActiveState,SubState,MainPID,Result'],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except subprocess.TimeoutExpired:
        process = subprocess.CompletedProcess([], 1, stdout='', stderr='manager query timed out')
    service = dict(line.split('=', 1) for line in process.stdout.splitlines() if '=' in line)
    stopped = (service.get('LoadState') == 'not-found'
               or service.get('ActiveState') in {'inactive', 'failed'})
    reports, errors = [], []
    for path in sorted(archive.glob('*/DS*-r*/*/report.json')):
        try:
            report = json.loads(path.read_text())
            reports.append(dict(path=str(path), statuses=report['statuses']))
        except (OSError, ValueError, KeyError) as exc:
            errors.append(dict(path=str(path), error=str(exc)))
    return dict(
        observed_at_unix=time.time(), service=service,
        service_error=process.stderr.strip() if process.returncode else None,
        service_stopped=stopped, reports=reports, read_errors=errors,
        expected_workers=expected, reported_workers=len(reports),
        all_reports_complete=(len(reports) == expected and not errors
                              and all(row['statuses'] == {'complete': 1} for row in reports)),
        scientific_validation='requires separate public/native/archive audit',
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unit', required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-workers', type=int, default=16)
    parser.add_argument('--interval', type=int, default=300)
    args = parser.parse_args(argv)
    if args.interval < 300 or args.expected_workers < 1:
        parser.error('Use an interval of at least 300 seconds and a positive worker count')
    if args.output.resolve().is_relative_to('/mnt/qnap01'):
        parser.error('Output must be outside QNAP')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    while True:
        status = snapshot(args.unit, args.archive, args.expected_workers)
        temporary = args.output.with_suffix('.tmp')
        temporary.write_text(json.dumps(status, indent=2) + '\n')
        temporary.replace(args.output)
        if status['service_stopped']:
            print(json.dumps(status))
            return 0 if status['all_reports_complete'] else 1
        time.sleep(args.interval)


if __name__ == '__main__':
    raise SystemExit(main())
