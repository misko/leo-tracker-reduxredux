"""Scan-disjoint confirmation of frozen opposite-RX native-curve recovery.

Uses saved native tracking contracts only. Cases are sealed before new native
pairs or position results are measured. This remains same-site confirmation.
"""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np
import probe_ds23_reception_anchor_ratio as pairs
import inventory_ds23_cross_RX_curves as inventory
import probe_ds23_cross_RX_curves_position as position
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_cross_RX_curves_confirmation'
BULK=Path('/srv/bulk/leo/research/ds23-cross-RX-curves-confirmation-20261021')


def configure():
    pairs.OUT=OUT/'pairs';pairs.BULK=BULK/'pairs'
    inventory.OUT=OUT/'inventory';inventory.BULK=BULK/'inventory';inventory.SOURCE=pairs.OUT/'evaluation.json'
    position.OUT=OUT/'position';position.BULK=BULK/'position'
    for p in [pairs.OUT,pairs.BULK,inventory.OUT,inventory.BULK,position.OUT,position.BULK]:p.mkdir(parents=True,exist_ok=True)


def stage(function,jobs):
    with ProcessPoolExecutor(max_workers=6) as pool:
        futures={pool.submit(function,j):j for j in jobs};rows=[]
        for f in as_completed(futures):
            try:rows.append(f.result())
            except Exception as exc:rows.append(dict(status='failed',job=futures[f],error=repr(exc)))
    return rows


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True)
    source=ROOT/'reports/2026_10_20_ds23_combined_recovery_full/protocol.json';roots=read(source)['input_roots']
    excluded=set(read(ROOT/'reports/2026_10_21_ds23_reception_anchor_ratio/protocol.json')['cases'])
    eligible=sorted(c for c,r in roots.items() if c not in excluded and Path(r).resolve()==pairs.SOURCE.resolve())
    cases=sorted(np.random.default_rng(2026102104).choice(eligible,20,replace=False).tolist())
    protocol=dict(cases=cases,seed=2026102104,excluded_development_cases=sorted(excluded),workers=6,
        sample_sealed_before_new_native_pairs_or_localization=True,same_site_not_new_location=True,
        no_GPS_future_TLE_new_RF_or_threshold_retuning=True,
        parent_position_protocol_sha256=sha(ROOT/'reports/2026_10_21_ds23_cross_RX_curves_position_v2/protocol.json'),
        source_sha256={p.name:sha(p) for p in [Path(__file__),Path(pairs.__file__),Path(inventory.__file__),Path(position.__file__)]})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('native curve confirmation protocol changed')
    if not path.exists():write(path,protocol)
    configure()
    paired=stage(pairs.one,cases);write(pairs.OUT/'evaluation.json',dict(rows=paired,all_terminal=True))
    if any(r['status']!='complete' for r in paired):raise ValueError('confirmation native-pair extraction failed')
    inventories=stage(inventory.one,cases);write(inventory.OUT/'inventory.json',dict(rows=inventories,all_terminal=True))
    if any(r['status']!='complete' for r in inventories):raise ValueError('confirmation curve inventory failed')
    results=stage(position.one,[r for r in inventories if r['fragments']])
    write(position.OUT/'execution.json',dict(rows=results,all_terminal=True,failures=[r for r in results if r['status']!='complete']))
    write(OUT/'execution.json',dict(all_terminal=True,cases=len(cases),offering_cases=sum(bool(r['fragments']) for r in inventories),
        qualified_native_points=sum(r['qualifying_curved_points'] for r in inventories),
        qualified_original_points=sum(r['qualifying_original_points'] for r in inventories),
        complete_position_trials=len(results),accepted_cases=sum(r.get('accepted',False) for r in results),
        failures=[r for r in results if r['status']!='complete']))


if __name__=='__main__':main()
