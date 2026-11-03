"""Run the three window-accounted selection methods from a frozen shared pool."""
import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

from association_search import Search, Settings
from cohort import digest
from discovery import ARMS
from numeric_data import load


def run(directory, *, penalty=10., gate=600., timing_sigma=1.):
    started = time.monotonic()
    data = load(directory, top_only=False)
    source = directory/'discovery/candidate-pool.json'
    pool = json.loads(source.read_text())
    if pool['status']!='complete' or pool['original_rows']!=data.original_rows.tolist():
        raise ValueError('candidate pool incomplete or observation order mismatch')
    for path, expected in pool['signature']['sources'].items():
        if digest(Path(path).read_bytes())!=expected:
            raise ValueError(f'candidate pool source changed: {path}')
    if gate>pool['signature']['gate_hz']:
        raise ValueError('selection gate exceeds discovery envelope')
    settings = Settings(penalty=penalty,tolerance_hz=gate,timing_sigma_s=timing_sigma)
    target = directory/f'selection-p{penalty:g}-g{gate:g}-t{timing_sigma:g}.json'
    implementation = [Path(__file__),Path(__file__).with_name('association_search.py')]
    signature = dict(pool_sha256=digest(source.read_bytes()),settings=asdict(settings),
                     implementation={str(p):digest(p.read_bytes()) for p in implementation})
    if target.exists():
        saved = json.loads(target.read_text())
        if saved['signature']!=signature:
            raise ValueError('selection signature mismatch')
        return target
    results = {}
    for arm in ARMS:
        results[arm] = {}
        for method, allowed, passes in (
            ('greedy',data.top_mask,0),('replacement',data.top_mask,3),('alternatives',None,3)):
            search = Search(pool['arms'][arm],data.group,data.times,data.receiver,data.channel,
                            allowed=allowed,settings=settings)
            value = search.run(maximum_passes=passes)
            for key in ('initial','final'):
                for assigned in value[key]['assignments']:
                    assigned['original_row_index'] = int(data.original_rows[assigned['row_index']])
            results[arm][method] = value
            final = value['final']
            print('SELECT',directory.name,arm,method,final['assigned'],'/',final['denominator'],
                  'satellites',final['satellites'],'objective',final['objective'],flush=True)
    record = dict(signature=signature,arms=results,elapsed_s=time.monotonic()-started,
                  calibration_warnings=pool['signature'].get('calibration_warnings',[]),
                  scope='Conditional known-roof in-sample selection. Receiver calibration is cross-fitted; identities and timing modes are searched on the entire scan. Not held-out identity accuracy.',
                  accounting='One associated candidate at most per original passing RX/channel/probe window; alternatives replace, never add to, that window count.')
    with target.open('x') as stream:
        json.dump(record,stream,allow_nan=False)
    return target


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path)
    p.add_argument('--penalty',type=float,default=10.)
    p.add_argument('--gate',type=float,default=600.)
    p.add_argument('--timing-sigma',type=float,default=1.)
    a=p.parse_args()
    run(a.directory,penalty=a.penalty,gate=a.gate,timing_sigma=a.timing_sigma)
