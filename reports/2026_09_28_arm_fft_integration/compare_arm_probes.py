"""Pair ARM probe candidates and quantify the intentionally approximate grid."""
import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    path=Path(__file__).resolve().parent.parent/'2026_09_28_arm_coarse_tiles/compare_probes.py'
    spec=importlib.util.spec_from_file_location('frozen_compare',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    result=module.compare(args.baseline,args.candidate)
    for row in result['rows']:
        name=row['label']+'.f64'
        a=np.fromfile(args.baseline/name,dtype='<f8');b=np.fromfile(args.candidate/name,dtype='<f8')
        assert a.shape==b.shape
        assert np.array_equal(np.isfinite(a),np.isfinite(b))
        finite=np.isfinite(a)
        row['maximum_grid_difference']=float(np.max(abs(a[finite]-b[finite]))) if finite.any() else 0
    result['scope']='Candidate objects must be identical; unselected proposal grid cells may differ.'
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['by_rate'],indent=2))
    assert result['all_candidates_identical']
