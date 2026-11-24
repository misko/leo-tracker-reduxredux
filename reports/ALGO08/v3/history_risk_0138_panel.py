"""Append the prospectively chosen ordinary full-20 ms transfer to five saved jobs."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from history_risk_route_panel import FIVE_CASE_SHA256, read_sealed_panel, reduction


CASE = 'DS30-0138'
KEY = '0138'
PREVIOUS = ('0160', '0316', '0374', '0402', '0169')


def summarize(earlier, newest, preflight, seal):
    if tuple(earlier['case_order']) != PREVIOUS or newest['case'] != CASE:
        raise ValueError('Unexpected first five cases or prospective sixth case')
    old = earlier['enrolled']
    portable = newest['binding']['input']['portable']
    router = newest['binding']['input']['sources']['history_risk_route.py']
    if (not newest['binding']['ordinary_renderer'] or not newest['saved_only'] or not newest['no_waveform']
            or newest['binding']['input']['issued'] != 6773 or not newest['named_parity']['complete']
            or not newest['prior_named_terminal_equal'] or not portable
            or any(row['source_stage']['sources']['history_risk_route.py'] != router for row in old.values())
            or any(row['grid_points'] != 179 for row in newest['coverage'].values())):
        raise ValueError('Handle this result as a separate transfer; the positive cohort scope differs')
    by_case = {key: old[key] for key in PREVIOUS}
    by_case[KEY] = dict(result=newest, source_stage=preflight, result_sha256=seal)
    totals = {}
    for clock, charge in (('elapsed_s', 'elapsed_ns'), ('cpu_s', 'cpu_ns')):
        rows = list(by_case.values())
        stock = [r['result']['archive_stock_clock'][clock] for r in rows]
        children = [r['result']['clock'][clock] for r in rows]
        routed = [elapsed+r['source_stage']['preflight'][charge]/1e9 for elapsed,r in zip(children, rows, strict=True)]
        totals[clock] = dict(child=reduction(stock, children), preflight_charged=reduction(stock, routed))
    return dict(case_order=list(by_case), enrolled=by_case, totals=totals, saved_only=True,
                prior_panel_receipt_sha256=FIVE_CASE_SHA256)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    args = p.parse_args()
    result = (args.root/'result.json').read_bytes()
    latest = json.loads(result)
    stage = (args.root/'routed/route-binding.json').read_bytes()
    if sha256(stage).hexdigest() != latest['binds']['routed/route-binding.json']:
        raise ValueError('The prospective result must bind its own recorded admission clock')
    print(json.dumps(summarize(read_sealed_panel(5), latest, json.loads(stage), sha256(result).hexdigest()),
                     indent=2, sort_keys=True, allow_nan=False))
