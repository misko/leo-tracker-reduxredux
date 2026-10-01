"""Admit sealed pair constituents and verify real quad state transfer without fitting."""
import argparse
import json
from pathlib import Path
import numpy as np
from run_window import prepare_window
from run_constituent_pair import save,digest,verify_sources
from recursive_quad_starts import quad_starts,remaining_quad_budget

HERE=Path(__file__).resolve().parent


def prepare(unit):
    inputs={};sources={}
    def load(path):
        assert digest(path)==path.with_suffix('.sha256').read_text().strip()
        inputs[str(path.resolve())]=digest(path);return json.loads(path.read_text())
    selection=load(HERE/'selection.json')
    binding=next(u for u in selection['evaluation_units'] if u['unit_id']==unit)
    assert binding['size']==4
    pairs=[next(u for u in selection['evaluation_units'] if u['size']==2 and u['scans']==binding['scans'][i:i+2]) for i in [0,2]]
    records=[]
    for pair in pairs:
        name=pair['unit_id'];directory=HERE/'constituent-pair-v3'/name
        audit=load(directory/'evaluation.json');assert len(audit['rows'])==1
        row=audit['rows'][0];assert row['unit']==name and row['accepted'],'constituent failed audit'
        receipt=load(directory/(name+'.json'));launch=load(directory/(name+'.launch.json'));frozen=load(directory/'sources.json')
        assert row['receipt_sha256']==launch['receipt_sha256']==digest(directory/(name+'.json'))
        assert launch['freeze_sha256']==digest(directory/'sources.json')
        assert launch['returncode']==0 and launch['within_budget'] and not launch['timed_out']
        assert receipt['binding']==pair and receipt['best']['converged']
        assert receipt['best']==min(receipt['fits'],key=lambda f:f['objectives'][-1])
        assert receipt['config']['prior_radius_km']==250 and receipt['config']['height_m_msl']==30.48
        verify_sources(frozen['source_sha256']);verify_sources(frozen['inputs'])
        verify_sources(receipt['source_sha256']);verify_sources(receipt['inputs'])
        inputs.update(frozen['inputs']);sources.update(frozen['source_sha256'])
        records.append((receipt,launch))
    actual,scans,columns,precision,ports=prepare_window(unit);assert actual==binding
    offset=0
    for (receipt,_),pair in zip(records,pairs,strict=True):
        pair_inputs={k:v for scan,_,_ in scans[offset:offset+2] for k,v in scan.inputs.items()}
        assert receipt['inputs']==pair_inputs
        assert receipt['height']==scans[offset][1].input_bindings
        old_precision=np.asarray(receipt['precision'])
        for j,local_columns in enumerate(receipt['columns']):
            np.testing.assert_array_equal(old_precision[local_columns],precision[columns[offset+j]])
        offset+=2
    states=[np.asarray(r['best']['mean']) for r,_ in records]
    starts=quad_starts(states,[p['scans'] for p in pairs],[r['columns'] for r,_ in records],
                      binding['scans'],columns,len(precision))
    for index,(receipt,_) in enumerate(records):
        for j,mapping in enumerate(receipt['columns']):
            expected=np.asarray(receipt['best']['mean'])[mapping][2:]
            for start in starts:np.testing.assert_array_equal(start[columns[index*2+j]][2:],expected)
    cost,remaining=remaining_quad_budget([launch['elapsed_seconds'] for _,launch in records])
    inputs.update({k:v for scan,_,_ in scans for k,v in scan.inputs.items()})
    return binding,records,scans,columns,precision,ports,starts,cost,remaining,inputs,sources


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name',required=True);args=parser.parse_args()
    assert Path(args.name).name==args.name
    rows=[];inputs={};sources={}
    for unit in ['DS9-B01-Q','DS10-B01-Q','DS11-B01-Q']:
        binding,records,scans,columns,precision,ports,starts,cost,remaining,used,source=prepare(unit)
        inputs.update(used);sources.update(source)
        rows.append(dict(unit=unit,scans=binding['scans'],dimension=len(precision),tracks=len(ports),
            starts=starts[:,:2].tolist(),constituent_cost_s=cost,remaining_s=remaining,
            nuisance_transfer_exact=True,prior_bindings_equal=True,input_bindings_equal=True))
    sources.update({str(Path(__file__).resolve()):digest(__file__),str(HERE/'recursive_quad_starts.py'):digest(HERE/'recursive_quad_starts.py')})
    save(HERE/(args.name+'.json'),dict(rows=rows,input_sha256=inputs,source_sha256=sources,
        qualification='No fit or reference scoring. Audited pair winners transferred by scan identity; nuisance states, priors and prepared inputs verified. Costs are historical charged pair launch totals.'))
    print(json.dumps(rows,indent=2),flush=True)


if __name__=='__main__':main()
