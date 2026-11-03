import unittest

from policy import select


class PolicyTests(unittest.TestCase):
    def test_qualification_only_not_position_or_score(self):
        challenger=dict(qualified=True,error_m=10000,score=-500)
        incumbent=dict(qualified=True,error_m=100,score=50)
        self.assertEqual(select(challenger,incumbent),(challenger,'challenger'))

    def test_fallback_and_baseline_failure(self):
        incumbent=dict(qualified=True)
        self.assertEqual(select(None,incumbent),(incumbent,'iid_fallback'))
        self.assertEqual(select(dict(qualified=False),incumbent),(incumbent,'iid_fallback'))
        self.assertEqual(select(dict(qualified=True),None),(None,'failure'))


if __name__=='__main__':
    unittest.main()
