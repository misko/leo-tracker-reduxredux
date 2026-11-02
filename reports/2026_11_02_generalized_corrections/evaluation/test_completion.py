import importlib.util
import json
import multiprocessing
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

spec=importlib.util.spec_from_file_location('coverage_completion',Path(__file__).with_name('complete_coverage.py'))
completion=importlib.util.module_from_spec(spec);spec.loader.exec_module(completion)


class CompletionTests(unittest.TestCase):
    def test_imported_frozen_worker_module_is_pickleable_for_pool(self):
        record=dict(selected=None,baseline={arm:dict(objective=1.,associated=2) for arm in completion.driver.ARMS})
        with multiprocessing.get_context('fork').Pool(1) as pool:
            result=pool.apply_async(completion.driver.fallback,(record,)).get(timeout=10.)
        self.assertEqual(result['c0']['source'],'exact_saved_ALGO07')

    def test_manager_only_empty_receipt_is_eligible(self):
        with TemporaryDirectory() as temp:
            self.assertFalse(completion.attempt_evidence(dict(status='total_deadline_fallback'),temp)['started'])

    def test_started_checkpoint_prohibits_retry_without_completed_cell(self):
        with TemporaryDirectory() as temp:
            Path(temp,'checkpoint_at_total_deadline.json').write_text('{}')
            self.assertTrue(completion.attempt_evidence(dict(status='total_deadline_fallback'),temp)['started'])

    def test_atomic_write_temporary_and_engine_directory_prohibit_retry(self):
        for artifact in ('result.json.tmp','A-c0.checkpoint.json.tmp','engine'):
            with TemporaryDirectory() as temp:
                path=Path(temp,artifact)
                path.mkdir() if artifact=='engine' else path.write_text('{}')
                self.assertTrue(completion.attempt_evidence(dict(status='total_deadline_fallback'),temp)['started'])

    def test_prior_protocol_identity_and_duplicates_are_rejected(self):
        record=dict(case='T',dataset='T',input_sha256='input',identities=['recording'])
        good=dict(record,status='total_deadline_fallback',protocol_sha256='seal')
        for rows,packet_seal in [([dict(good,protocol_sha256='wrong')],'seal'),
                                  ([dict(good,input_sha256='wrong')],'seal'),
                                  ([good,good],'seal'),([good],'wrong')]:
            with TemporaryDirectory() as temp:
                path=Path(temp,'results.json')
                path.write_text(json.dumps(dict(workers_joined=True,protocol_sha256=packet_seal,available=len(rows),rows=rows)))
                with self.assertRaises(ValueError):
                    completion.eligible_records(dict(cases=[record]),[path],['seal'])

    def test_every_actual_worker_receipt_or_cell_prohibits_retry(self):
        with TemporaryDirectory() as temp:
            for row in [dict(status='failed'),dict(status='total_deadline_fallback',wall_seconds=1.),
                        dict(status='total_deadline_fallback',numerical_trigger_diagnostics={})]:
                self.assertTrue(completion.attempt_evidence(row,temp)['started'])
            Path(temp,'A-c0.checkpoint.json').write_text('{}')
            self.assertTrue(completion.attempt_evidence(dict(status='total_deadline_fallback'),temp)['started'])


if __name__=='__main__':unittest.main()
