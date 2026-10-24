"""Independent physical-ID and paired-policy output accounting."""
import json
from pathlib import Path
import numpy as np

OUT=Path(__file__).resolve().parents[1]


def main():
    cases=json.loads((OUT/'sample.json').read_text())['selected'];rows=[]
    for m in cases:
        case=m['dataset_label']; path=OUT/'results'/(case+'.json')
        if not path.exists():
            rows.append(dict(case=case,position_comparison_available=False));continue
        record=json.loads(path.read_text())
        obs=json.loads((OUT/case/'observations.json').read_text())
        allids={o['observation_id'] for o in obs}
        baseline=record['methods']['baseline']
        for method,r in record['methods'].items():
            if not r.get('accepted'):continue
            for arm,c in r['coverage'].items():
                saved=r['arms'][arm]
                gates=saved['gates']['tracks']+saved.get('linear_gates',[])
                assert gates and all(t['compatible'] for t in gates)
                ids=c['accepted_observation_ids'];b=baseline['coverage'][arm]['accepted_observation_ids']
                assert len(ids)==len(set(ids))==c['associated']
                assert set(ids)<=allids and c['total_GLRT']==len(allids)
                if method!='algo02_historical':assert set(b)<=set(ids)
                np.testing.assert_allclose(c['percent'],100*len(ids)/len(allids),atol=1e-10)
                if method=='native_fixed':
                    np.testing.assert_array_equal(r['arms'][arm]['endpoint_east_north_km'],baseline['arms'][arm]['endpoint_east_north_km'])
        rows.append(dict(case=case,position_comparison_available=True,status=record['status'],
                         original_physical_IDs=True,unique_ownership=True,native_fixed_position_identical=True))
    result=dict(rows=rows,population=len(cases),comparisons=sum(r['position_comparison_available'] for r in rows))
    (OUT/'output_audit.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
