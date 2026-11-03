import copy
import unittest
import json
import tempfile
from pathlib import Path
from cohort import digest
from freeze_final_settings import decide,read_freeze


class FinalSettingsTests(unittest.TestCase):
    def test_bare_file_is_not_a_valid_test_unlock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'final-settings.json';target.write_text('{}')
            with self.assertRaisesRegex(ValueError,'invalid final'):read_freeze(root)
            cohort=root/'cohort-v2.json';cohort.write_text('{}')
            source=root/'evidence.json';source.write_text('{}')
            target.write_text(json.dumps(dict(schema='offline-final-settings/v1',cohort_sha256=digest(cohort.read_bytes()),
                                              sources={str(source):digest(source.read_bytes())})))
            read_freeze(root)
            source.write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError,'evidence changed'):read_freeze(root)

    def fixture(self):
        protocol=dict(validation_scans=['V1','V2','V3','V4'],
                      configurations=[dict(name=n) for n in ('baseline','tight','wide','curve')])
        rows=[dict(scan=s,split='validation',configuration=c['name'],arm=a,eligible=True,
                   error_m=1000 if c['name']=='baseline' else 750 if c['name']=='tight' else 1100)
              for s in protocol['validation_scans'] for c in protocol['configurations'] for a in ('fitted-c','zero-c')]
        return protocol,rows

    def test_complete_matched_matrix_required(self):
        p,rows=self.fixture()
        for bad in (rows[:-1],rows+[rows[0]]):
            with self.assertRaisesRegex(ValueError,'complete unique'):decide(p,bad)

    def test_selects_qualifying_challenger_without_using_test_rows(self):
        p,rows=self.fixture();rows.append(dict(split='locked_test',error_m=0))
        result=decide(p,rows)
        self.assertEqual(result['selected_configuration'],'tight')
        self.assertEqual(result['status'],'validation_selected')

    def test_failed_zero_distance_cannot_win(self):
        p,rows=self.fixture()
        for r in rows:
            if r['configuration']!='baseline':r.update(error_m=0,eligible=False)
        result=decide(p,rows)
        self.assertEqual(result['selected_configuration'],'baseline')
        self.assertEqual(result['status'],'inconclusive_baseline_reference')

    def test_more_failures_disqualify_even_large_improvement(self):
        p,rows=self.fixture()
        next(r for r in rows if r['configuration']=='tight' and r['arm']=='fitted-c')['eligible']=False
        self.assertEqual(decide(p,rows)['selected_configuration'],'baseline')

    def test_less_than_twenty_percent_does_not_win(self):
        p,rows=self.fixture()
        for r in rows:
            if r['configuration']=='tight':r['error_m']=810
        self.assertEqual(decide(p,rows)['status'],'baseline_retained_no_qualifying_challenger')
