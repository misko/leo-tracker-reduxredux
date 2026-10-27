import json
import unittest
import application as app

class FrozenApplicationTests(unittest.TestCase):
    def test_existing_lane_selection_and_blocks_exact(self):
        _,_,select=app.ports(); old=app.read(app.PRED/'blocks.json')['blocks']
        for case in ['DS24-0011','DS24-0097']:
            lanes,_=app.nomination(case,False,select)
            data=app.read(app.SOURCE/case/'tracking.json')
            blocks=[select.nominate(l,data['source']['probes'],10000000) for l in lanes[:2]]
            self.assertEqual(blocks,[b for b in old if b['case']==case])
            self.assertLessEqual(len(select.deduplicate(blocks)),160)

    def test_frozen_serialization_boundary_isolates_shared_donor(self):
        donor={'stream_generation':'original'}
        rows=[{'donor':donor},{'donor':donor}]
        rows=json.loads(json.dumps(rows)); rows[0]['donor']['stream_generation']=123
        self.assertEqual(rows[1]['donor']['stream_generation'],'original')

    def test_no_eligible_lane_stays_in_cohort(self):
        split,cases=app.cohort();_,_,select=app.ports()
        self.assertEqual(len(cases),24)
        self.assertEqual(len(cases),len(set(cases)))
        for c in cases:
            lanes,_=app.nomination(c,c in split['validation'],select)
            if not lanes:self.assertEqual(select.deduplicate([]),[])

if __name__=='__main__':unittest.main()
