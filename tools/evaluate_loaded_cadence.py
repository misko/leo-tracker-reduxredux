"""Apply the predeclared throughput gate to an already verified finite schedule."""
import argparse
import json
import math
from pathlib import Path


def evaluate(schedule, period_s, minimum_loaded=3):
    if not schedule.get('fixed_cadence_and_capacity_passed'):
        raise ValueError('unverified schedule')
    if not math.isfinite(period_s) or period_s <= 0:
        raise ValueError('invalid period')
    if type(minimum_loaded) is not int or minimum_loaded < 1:
        raise ValueError('invalid minimum loaded intervals')
    scans = schedule['scans']
    if not scans or [s['scan'] for s in scans] != list(range(len(scans))):
        raise ValueError('incomplete scan inventory')
    if scans[-1]['downstream_finished_before_next_scan_ready'] is not None:
        raise ValueError('missing final drain boundary')
    loaded = []
    for scan in scans[:-1]:
        duration = scan['downstream_wall_s']
        ready = scan['downstream_finished_before_next_scan_ready']
        if not math.isfinite(duration) or duration < 0 or type(ready) is not bool:
            raise ValueError('invalid loaded interval')
        loaded.append({'scan': scan['scan'], 'wall_s': duration,
                       'margin_s': period_s-duration,
                       'finished_before_next_scan_ready': ready,
                       'passed': duration < period_s and ready})
    enough = len(loaded) >= minimum_loaded
    return {'passed': enough and all(s['passed'] for s in loaded),
            'period_s': period_s, 'minimum_loaded_intervals': minimum_loaded,
            'sufficient_loaded_intervals': enough, 'loaded_intervals': loaded,
            'excluded_drain_scan': scans[-1]['scan'],
            'scope': 'Finite recorded-load throughput only; independent scientific and lossless checks required'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    report = args.report
    protocol = json.loads((report/'protocol.json').read_text())
    science = json.loads((report/'evaluation.json').read_text())
    schedule = science['schedule']
    result = evaluate(schedule, protocol['period_ms']/1000)
    result['scientific_and_lossless_passed'] = science.get('passed') is True
    result['passed'] &= result['scientific_and_lossless_passed']
    with (report/'loaded-cadence-evaluation.json').open('x') as output:
        json.dump(result, output, indent=2)
        output.write('\n')
    print(json.dumps(result))
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
