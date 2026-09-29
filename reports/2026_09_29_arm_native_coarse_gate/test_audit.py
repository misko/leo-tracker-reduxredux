import json
from pathlib import Path
import tempfile
import unittest

import audit

class VariableInventoryLoaderTest(unittest.TestCase):
    def record(self, count=0):
        rows=[]
        for receiver,probe in audit.frozen.WINDOW_KEYS:
            rows.append({'receiver_id':receiver,'probe_index':probe,
                         'candidate_count':count,'candidates':[{'refined_epoch':0} for _ in range(count)]})
        return {'context':{'session_id':'unit','visit_index':1},'returncode':0,'stderr':'','rows':rows}
    def write(self, record):
        path=Path(tempfile.mkstemp(suffix='.jsonl')[1]);path.write_text(json.dumps(record)+'\n');return path
    def test_accepts_post_gate_variable_counts(self):
        path=self.write(self.record(3));self.addCleanup(path.unlink)
        native=audit.load_gated(path);row=native[('unit',1)][next(iter(audit.frozen.WINDOW_KEYS))]
        self.assertEqual(row['candidate_count'],3);self.assertEqual(row['candidates'][0]['epoch'],0)
    def test_rejects_count_payload_mismatch(self):
        record=self.record(1);record['rows'][0]['candidates']=[];path=self.write(record);self.addCleanup(path.unlink)
        with self.assertRaises(AssertionError):audit.load_gated(path)
    def test_rejects_count_above_inventory_limit(self):
        path=self.write(self.record(9));self.addCleanup(path.unlink)
        with self.assertRaises(AssertionError):audit.load_gated(path)
    def test_labels_unequal_emitted_inventory(self):
        path=self.write(self.record(3));self.addCleanup(path.unlink);native=audit.load_gated(path)
        manifest={'selected':[{'session_id':'unit','visit_index':1,'rate_hz':2500000}]}
        result={'totals':{'candidates':176},'by_rate':{'2500000':{'candidates':176}}}
        audit.annotate_candidate_inventories(result,manifest,native)
        self.assertEqual(result['totals']['reference_candidate_entries'],176)
        self.assertEqual(result['totals']['emitted_candidate_entries'],66)
        self.assertEqual(result['by_rate']['2500000']['emitted_candidate_entries'],66)
        self.assertEqual(result['totals']['candidates_meaning'],'frozen reference inventory')

if __name__=='__main__':unittest.main()
