import copy
import unittest
from grouped_split import randomized_groups


def row(n,utc=None,start=None):
    return {'track_id':'t'+str(n),'observation_id':str(n),'utc_ns':n*100 if utc is None else utc,
            'sample_start':n*10 if start is None else start,'sample_end':(n*10 if start is None else start)+10,
            'source_group_id':'g','opportunity_key':['s',n],'physical_pair_key':None}


class Tests(unittest.TestCase):
    def test_order_stability(self):
        rows=[row(n) for n in range(20)]
        self.assertEqual(randomized_groups(rows,'s',block_ns=100),randomized_groups(rows[::-1],'s',block_ns=100))

    def test_cross_track_and_boundary_union(self):
        rows=[row(0,utc=99),row(1,utc=101,start=5),row(2,utc=199)]
        out=randomized_groups(rows,'s',block_ns=100)
        self.assertEqual(len(out['groups']),1)
        self.assertEqual(len(out['groups'][0]['observations']),3)

    def test_pair_union(self):
        rows=[row(0),row(1)]
        for r in rows:r['physical_pair_key']=['same-pair']
        self.assertEqual(len(randomized_groups(rows,'s',block_ns=100)['groups']),1)

    def test_outcomes_and_old_mask_ignored(self):
        a=[row(n) for n in range(10)]; b=copy.deepcopy(a)
        for r in b:r.update(training=True,split_label='A',frequency=999,matched=True)
        self.assertEqual(randomized_groups(a,'s',block_ns=100),randomized_groups(b,'s',block_ns=100))

    def test_seed_changes_assignment(self):
        rows=[row(n) for n in range(40)]
        a=randomized_groups(rows,'s',seed=1,block_ns=100)
        b=randomized_groups(rows,'s',seed=2,block_ns=100)
        mapping=lambda x:{tuple(g['time_blocks']):g['partition'] for g in x['groups']}
        self.assertNotEqual(mapping(a),mapping(b))

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):randomized_groups([row(0),row(0)],'s')


if __name__=='__main__':unittest.main()
