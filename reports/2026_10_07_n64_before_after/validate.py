"""Check the completed cohort, replay grid decisions, and verify score selection."""
from dataclasses import asdict
import csv
import json
from pathlib import Path
import numpy as np
import experiment as e
import data
from leo.analysis.regional_position_search import SpatialSearch,distinct_basins

def main():
    root=e.HERE;protocol=json.loads((root/'protocol.json').read_text())
    summary=json.loads((root/'summary.json').read_text())
    assert summary['complete'] and summary['completed_phases']==128
    assert len(summary['rows'])==256 and len(summary['paired'])==128
    assert len(summary['audits'])==sum(r['accepted'] for r in summary['rows'])
    with (root/'comparison.csv').open() as handle:
        wide=list(csv.DictReader(handle))
    assert [r['label'] for r in wide]==protocol['labels']
    assert len(wide)==64
    grid_checks=[];selection_checks=[];run_counts={'zero-c':0,'fitted-c':0}
    for label in protocol['labels']:
        for phase,cfg in protocol['phases'].items():
            folder=root/'results'/label/phase
            search=json.loads((folder/'search.json').read_text())
            result=json.loads((folder/'result.json').read_text())
            lookup={(r['east_km'],r['north_km']):r['score'] for r in search['search']['evaluations']}
            replay,meta=e.edge_grid.search(lambda points:[lookup[tuple(xy)] for xy in points],
                                          levels=cfg['levels'],budget=400,edge_policy=cfg['edge'])
            assert asdict(replay)=={**search['search'],'evaluations':tuple(search['search']['evaluations'])}
            assert len(replay.evaluations)==400
            assert meta==search['edge']
            supported=SpatialSearch(tuple(p for p in replay.evaluations if p.score<1e100),replay.deferred_cells,replay.stop_reason)
            basins=distinct_basins(supported,count=3,minimum_separation_km=12.5)
            assert [asdict(b) for b in basins]==result['basins']
            candidates=[]
            for region_path in (folder/'regions').glob('*.json'):
                region=json.loads(region_path.read_text())
                candidates.extend(dict(r,point=region['point'],local_radius_km=region['local_radius_km']) for r in region['candidates'])
                for r in region['runs']:run_counts[r['arm']]+=1
                if phase=='after':
                    for r in region['candidates']:assert max(abs(np.asarray(r['vector'])[[3,5]]))<=60.+1e-6
                    if 'calibration' in region:
                        for name in ('prefit','postfit'):
                            assert max(abs(np.asarray(region['calibration'][name]['vector'])[[3,5]]))<=60.+1e-6
            for arm in ('zero-c','fitted-c'):
                pool=[r for r in candidates if r['arm']==arm and r['feasible'] and r['converged']]
                expected=min(pool,key=lambda r:(r['selection_score'],r['point'],r['origin']),default=None)
                assert expected==result['selections'][arm]['result']
                if expected is not None and arm=='zero-c':assert expected['vector'][6]==0.
                selection_checks.append(dict(label=label,phase=phase,arm=arm,accepted=expected is not None))
            grid_checks.append(dict(label=label,phase=phase,points=len(replay.evaluations),replayed=True))
    assert run_counts['zero-c']==run_counts['fitted-c']
    for path,expected in protocol['sources'].items():assert data.digest(path)==expected,path
    e.write(root/'validation.json',dict(grid_checks=grid_checks,selection_checks=selection_checks,final_fit_calls=run_counts,
                                      accepted_original_score_audits=len(summary['audits']),all_checks_passed=True))
    files=['protocol.json','results.json','summary.json','comparison.csv','comparison_by_arm.csv','results_long.csv',
           'search_diagnostics.csv','findings.txt','validation.json','position_comparison.png','per_scan_errors.png',
           'summarize.py','validate.py','evaluation.json','N13_regression_diagnostic.json','N64_regression_diagnostic.json',
           'association_engine_audit.json','tests.log']
    e.write(root/'artifact_manifest.json',dict(files={name:data.digest(root/name) for name in files},
        input_metadata={label:data.digest(root/'inputs'/label/'inputs.json') for label in protocol['labels']}))
    print('PASS: 128 grid searches replayed; 256 arm selections checked; 64 CSV rows; original-score audits',len(summary['audits']),'; matched final calls',run_counts)

if __name__=='__main__':main()
