from copy import deepcopy
from pathlib import Path
import sys
import unittest
from derive_blocks import derive_blocks,perturb_excluded,payload,group_id,key

# A sealed metadata fixture is a test-only numerical oracle, never inference input.
sys.path.append(str(Path(__file__).resolve().parents[2]/'2026_10_17_dsx01_iteration4'/'cold_pipeline'))
from test_cold_pipeline import document


class BlockTests(unittest.TestCase):
    def test_alternation_and_boundary_exclusion_use_entire_probe(self):
        source=document();before=deepcopy(source)
        train,r=derive_blocks(source,training_parity=0)
        self.assertEqual([p['visit_index'] for p in train['source']['probes']],[0,1,4])
        self.assertEqual(r['held_keys'],[(3,1,0),(5,1,0)])
        self.assertEqual(r['boundary_keys'],[(2,0,0)])
        self.assertEqual(source,before)
        other,s=derive_blocks(source,training_parity=1)
        self.assertEqual(set(r['training_keys']),set(s['held_keys']))
        self.assertEqual(set(r['held_keys']),set(s['training_keys']))
        self.assertEqual(r['boundary_keys'],s['boundary_keys'])
        self.assertEqual(sum(len(p['candidates']) for p in train['source']['probes']),6)

    def test_all_excluded_cfo_scores_and_gates_leave_train_bytes_and_global_ids_unchanged(self):
        for parity in [0,1]:
            source=document();train,r=derive_blocks(source,training_parity=parity)
            changed=perturb_excluded(source,r);other,s=derive_blocks(changed,training_parity=parity)
            self.assertEqual(payload(train),payload(other));self.assertEqual(r,s)
            parent_ids={key(p):group_id(source['source'],key(p)) for p in source['source']['probes']}
            for p in train['source']['probes']:
                self.assertEqual(group_id(train['source'],key(p)),parent_ids[key(p)])
            self.assertNotEqual(payload(source),payload(changed))

    def test_invalid_duration_parity_or_duplicate_keys_rejected(self):
        for seconds in [0,-1,2.5,True]:
            with self.assertRaises(ValueError):derive_blocks(document(),block_seconds=seconds)
        for parity in [-1,2,True]:
            with self.assertRaises(ValueError):derive_blocks(document(),training_parity=parity)
        source=document();source['source']['probes'].append(deepcopy(source['source']['probes'][0]))
        with self.assertRaises(ValueError):derive_blocks(source)


if __name__=='__main__':unittest.main()
