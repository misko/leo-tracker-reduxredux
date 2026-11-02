import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

spec=importlib.util.spec_from_file_location('postfit_merge',Path(__file__).with_name('merge_results.py'))
merge=importlib.util.module_from_spec(spec);spec.loader.exec_module(merge)


class MergeTests(unittest.TestCase):
    def test_empty_remaining_queue_is_valid_without_inference_scheduler(self):
        with TemporaryDirectory() as temp:
            row=dict(case='T',status='complete')
            path=Path(temp,'results.json');path.write_text('{}')
            self.assertEqual(merge.never_started(dict(T=row),dict(T=dict(results_path=str(path)))),[])
        self.assertEqual(merge.never_started({},{}),[])

    def test_exact_later_row_replaces_only_manager_placeholder(self):
        with TemporaryDirectory() as temp:
            first=Path(temp,'first/results.json');second=Path(temp,'second/results.json')
            first.parent.mkdir();second.parent.mkdir()
            old=dict(case='T',status='total_deadline_fallback')
            new=dict(case='T',status='complete',wall_seconds=1.,nested=dict(exact=['unchanged',3]))
            first.write_text(json.dumps(dict(rows=[old])));second.write_text(json.dumps(dict(rows=[new])))
            rows,provenance=merge.merge_rows([(first,dict(rows=[old])),(second,dict(rows=[new]))])
            self.assertIs(rows['T'],new)
            self.assertEqual(provenance['T']['results_path'],str(second.resolve()))

    def test_started_row_cannot_be_replaced(self):
        with TemporaryDirectory() as temp:
            first=Path(temp,'first.json');second=Path(temp,'second.json')
            first.write_text('{}');second.write_text('{}')
            with self.assertRaisesRegex(ValueError,'started case'):
                merge.merge_rows([(first,dict(rows=[dict(case='T',status='failed')])),
                                  (second,dict(rows=[dict(case='T',status='complete')]))])


if __name__=='__main__':unittest.main()
