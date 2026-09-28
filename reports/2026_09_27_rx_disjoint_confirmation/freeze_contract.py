"""Bind input, model, and code before any disjoint predictive scores run."""
import json
from pathlib import Path
from select_cohort import sha

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent


def main():
    manifest=json.loads((HERE/'manifest.json').read_text())
    selected={s['capture']['session_id'] for s in manifest['sessions']}
    inventory=json.loads((HERE/'inventory.json').read_text())
    if len(selected)!=4 or selected!={r['session_id'] for r in inventory} or not all(r['ready'] for r in inventory):
        raise ValueError('incomplete inventory')
    old=REPORTS/'2026_09_27_roof_balanced_confirmation'
    direction=REPORTS/'2026_09_27_roof_direction_subset'
    pairing_members={r['session_id'] for r in json.loads((direction/'evaluation_inventory.json').read_text()) if r['split']=='calibration' and r['ready']}
    for name in ('mixture_calibration_polished.json','track_random_intercept_refined.json','ratio_random_intercept.json'):
        members=set(json.loads((old/name).read_text())['calibration_sessions'])
        if members!=pairing_members or members&selected:raise ValueError('calibration membership overlaps or differs')
    # Include research dependency modules and accepted scientific JSON receipts;
    # no raw corpus is copied, and cache inputs are bound separately.
    dirs=[old,direction,REPORTS/'2026_09_27_roof_geometry_confirmation',REPORTS/'2026_09_27_roof_location_geometry']
    paths=list(HERE.glob('*.py'))+[HERE/'PROTOCOL.md',HERE/'manifest.json',HERE/'inventory.json']
    for directory in dirs:paths.extend(directory.glob('*.py'))
    paths.extend([old/name for name in ('mixture_calibration_polished.json','track_random_intercept_refined.json','ratio_random_intercept.json','calibration_directions_data.json')])
    paths.extend([REPORTS/'2026_09_27_roof_location_geometry/topology_frequency_fixedpoint.json',direction/'pairing_summary.json',direction/'evaluation_inventory.json',direction/'model_rows.json'])
    paths.extend(REPORTS/'2026_09_27_rx_transfer_concentration'/name for name in ('grouped_split.py','conservative.py','verify_grouped_rebuild.py'))
    paths.extend(Path(r['cache_file']) for r in inventory)
    out={'session_ids':sorted(selected),'calibration_sessions':sorted(pairing_members),
         'files':{str(p):sha(p.read_bytes()) for p in sorted(set(paths))}}
    with (HERE/'contract.json').open('x') as stream:json.dump(out,stream,indent=2);stream.write('\n')
    print('CONTRACT_FROZEN',len(out['files']),sorted(selected))


if __name__=='__main__':main()
