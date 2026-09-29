"""Screen coarse-score cutoffs before implementing candidate pruning."""
import copy
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_09_28_arm_full_optimization'))
import independent_summary as frozen


def keep(candidate, threshold):
    return candidate['coarse_score'] >= threshold


def main():
    cohort=HERE.parent/'2026_09_29_arm_wave3_combined/host704'
    manifest=json.loads((cohort/'manifest.json').read_text())
    assert manifest['complete']
    assert frozen.sha256(cohort/'rows.jsonl') == manifest['rows_sha256']
    baseline_path=HERE.parent/'2026_09_28_ds7_large_arm/baseline-01/rows.jsonl'
    baseline=frozen.load_baseline(baseline_path)
    original=frozen.load_native(cohort/'rows.jsonl')
    results=[]
    for threshold in [0,.05,.1,.125,.15,.175,.2,.225,.25,.275,.3,.325,.35]:
        native=copy.deepcopy(original)
        retained=0
        for windows in native.values():
            for row in windows.values():
                row['candidates']=[c for c in row['candidates'] if keep(c,threshold)]
                row['candidate_count']=len(row['candidates'])
                retained+=len(row['candidates'])
                for c in row['candidates']:c['epoch']=c['refined_epoch']
        quality=frozen.summarize(manifest['selected'],baseline,native)
        results.append({'threshold':threshold,'retained_candidates':retained,'quality':quality})
        print(threshold,retained,quality['totals']['recovered_positive_hits'],flush=True)
    output={'scope':'offline counterfactual; fewer candidate GLRTs, all windows retained; no runtime claim',
            'input_sha256':manifest['rows_sha256'],'baseline_sha256':frozen.sha256(baseline_path),
            'runner_sha256':frozen.sha256(Path(__file__)),
            'matcher_sha256':frozen.sha256(Path(frozen.__file__)),'results':results}
    (HERE/'results.json').write_text(json.dumps(output,indent=2)+'\n')


if __name__=='__main__':main()
