"""Verify the new report's projection against all frozen original observations."""
import csv
import json
from pathlib import Path
import tempfile
from analyze import project,HERE,REPORTS,BASE

def main():
    with tempfile.TemporaryDirectory(prefix='leo-ungated-projection-check-',dir='/var/tmp') as tmp:
        out=Path(tmp)
        project(REPORTS/'2026_09_30_arm_full_scan_comparison/arm-v2',out)
        def joined(observations,mapping):
            keys={r['candidate_id']:(int(r['visit']),int(r['receiver_id']),int(r['candidate_rank']))
                  for r in csv.DictReader(mapping.open(),delimiter='\t')}
            return {keys[r['candidate_id']]:{k:v for k,v in r.items() if k!='candidate_id'}
                    for r in csv.DictReader(observations.open(),delimiter='\t')}
        expected=joined(BASE/'arm-observations.tsv',BASE/'arm-candidate-map.tsv')
        actual=joined(out/'observations.tsv',out/'candidate-map.tsv')
        assert expected.keys()==actual.keys()
        for key in expected:
            for field,value in expected[key].items():
                other=actual[key][field]
                if field in ['actual_rf_hz','measured_cfo_hz','exact_score','control_score','margin']:
                    assert float(value)==float(other),(key,field,value,other)
                else:assert value==other,(key,field,value,other)
        receipt={'original_rows_compared':len(expected),'all_source_groups_timestamps_lanes_scores_cfos_equal':True,
                 'candidate_ids':'New report provenance produces different IDs; comparison joins original visit/RX/rank'}
        (HERE/'projection-validation.json').write_text(json.dumps(receipt,indent=2)+'\n')
        print(json.dumps(receipt))

if __name__=='__main__':main()
