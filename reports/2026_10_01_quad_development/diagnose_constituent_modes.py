"""Compare fitted branches on identical observations; never select by geography."""
import argparse
import json
from pathlib import Path
import numpy as np
from run_constituent_pair import digest, save

HERE=Path(__file__).resolve().parent


def compare_fits(original,variant):
    for key in ['binding','columns','inputs','observations','precision']:
        assert original[key]==variant[key], f'incompatible {key}'
    a=original['best'];b=variant['best']
    assert len(a['associations'])==len(b['associations'])==len(original['observations'])
    starts=variant['fits']
    return dict(objective_change=b['objectives'][-1]-a['objectives'][-1],
        track_count=len(a['associations']),
        changed_assignments=sum(x!=y for x,y in zip(a['associations'],b['associations'],strict=True)),
        position_separation_m=float(np.linalg.norm(np.asarray(a['mean'][:2])-np.asarray(b['mean'][:2]))*1000),
        selected_start=b['seed_index'],
        starts=[dict(seed_index=f['seed_index'],converged=f['converged'],reason=f['reason'],
            iterations=f['iterations'],objective=f['objectives'][-1] if f['objectives'] else None,
            position_enu_km=f['mean'][:2]) for f in starts])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('snapshot',type=Path);parser.add_argument('--name',required=True)
    args=parser.parse_args();assert Path(args.name).name==args.name
    inputs={}
    def load(path):
        assert digest(path)==path.with_suffix('.sha256').read_text().strip()
        inputs[str(path.resolve())]=digest(path);return json.loads(path.read_text())
    snapshot=load(args.snapshot);rows=[]
    for entry in snapshot['rows']:
        if entry['variant'] is None or not entry['variant']['accepted'] or not entry['baseline']['accepted']:continue
        unit=entry['unit'];block=entry['baseline']['block_id']
        original_path=HERE/'independent-v2'/block/(unit+'.json')
        variant_path=HERE/'constituent-pair-v3'/unit/(unit+'.json')
        original=load(original_path);variant=load(variant_path)
        assert digest(original_path)==entry['baseline']['receipt_sha256']
        assert digest(variant_path)==entry['variant']['receipt_sha256']
        result=compare_fits(original,variant)
        rows.append(dict(unit=unit,**result))
    save(HERE/(args.name+'.json'),dict(rows=rows,input_sha256=inputs,source_sha256=digest(__file__),
        qualification='Diagnostic of accepted original/variant pairs with identical observation and candidate-input bindings. Assignment indices are comparable only within these bound ports. Changes do not verify satellite identities. Position separation is distance in the fitted ENU chart, not geographic-reference error. No fitted-state selection or new inference.'))
    print(json.dumps(rows,indent=2),flush=True)


if __name__=='__main__':main()
