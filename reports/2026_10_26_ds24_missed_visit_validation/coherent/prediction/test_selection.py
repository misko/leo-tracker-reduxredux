import copy
import unittest
import selection


def addition(oid,ch,rx,start):
    return dict(target_observation_id=oid,channel=ch,native_receiver_id=rx,status='new_native_exploratory_addition',
        existing_owner=False,native=dict(start_counter=start,stop_counter=start+20,edge='upper'))


class SelectionTests(unittest.TestCase):
    def test_new_native_tie_break_and_earliest_seed(self):
        rows=[addition('a',5,0,100),addition('b',6,1,200),addition('c',6,1,300),addition('d',6,1,50)]
        ranked=selection.lanes(dict(case='case',staged=rows),{'a','b','d'})
        self.assertEqual(ranked[0]['channel'],6)
        self.assertEqual(ranked[0]['seed_observation_id'],'d')
        changed=copy.deepcopy(rows)
        for r in changed:r.update(confirmation_cfo_hz=1e99,position_error_km=-1e99,confirmation_margin=.999)
        self.assertEqual(ranked,selection.lanes(dict(case='case',staged=changed),{'a','b','d'}))

    def test_lane_rule_does_not_force_distinct_channels(self):
        rows=[addition('a',5,0,100),addition('b',5,1,200),addition('c',6,0,300)]
        ranked=selection.lanes(dict(case='case',staged=rows),{'a','b','c'})
        self.assertEqual([(r['channel'],r['nominating_receiver_id'])for r in ranked[:2]],[(5,0),(5,1)])

    def test_closed_interval_cap_and_dedup_without_candidate_values(self):
        block=dict(case='case',channel=5,nominating_receiver_id=0,edge='upper',lane_rank=1,
            seed_native=dict(start_counter=240,stop_counter=260),seed_observation_id='seed')
        probes=[dict(channel=5,edge='upper',receiver_id=rx,visit_index=i,valid_start_counter=start,candidates=[dict(x=1)])
                for i,start in enumerate(range(0,501,5))for rx in [0,1]]
        nominated=selection.nominate(block,probes,10,window_samples=20)
        # Center250, closed[130,370], midpoint=start+10 includes start120and360.
        self.assertEqual(nominated['enumerated_paired_visits'],49)
        self.assertEqual(nominated['probes'][0]['valid_start_counter'],120)
        self.assertEqual(nominated['probes'][-1]['valid_start_counter'],360)
        self.assertNotIn('candidates',nominated['probes'][0])
        duplicate=dict(nominated,block_id='overlap')
        self.assertEqual(len(selection.deduplicate([nominated,duplicate])),49)
        wide=selection.nominate(block,probes,1000,window_samples=20)
        self.assertEqual(wide['retained_paired_visits'],80);self.assertTrue(wide['capped'])


if __name__=='__main__':unittest.main()
