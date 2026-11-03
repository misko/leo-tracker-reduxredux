import copy
import unittest
from run_fisher_positions import warning_only_cache_compatible,LEGACY_WARNING_ONLY_CHANGE


class PositionCacheTests(unittest.TestCase):
    def fixture(self):
        old=dict(inputs={'unchanged':1},probe_budget_s=8,implementation={
            '/report/position_search.py':LEGACY_WARNING_ONLY_CHANGE['position_search.py'],
            '/report/run_fisher_positions.py':LEGACY_WARNING_ONLY_CHANGE['run_fisher_positions.py'],
            '/report/fisher_position.py':'unchanged-math'})
        new=copy.deepcopy(old)
        new['implementation']['/report/position_search.py']='new-warning-opt-in'
        new['implementation']['/report/run_fisher_positions.py']='new-warning-driver'
        return old,new

    def test_known_warning_only_revision_can_be_numerically_audited(self):
        self.assertTrue(warning_only_cache_compatible(*self.fixture()))

    def test_other_math_inputs_budgets_and_unknown_revisions_rejected(self):
        for mutate in (lambda d:d['implementation'].update({'/report/fisher_position.py':'changed-math'}),
                       lambda d:d.update(probe_budget_s=9),lambda d:d['inputs'].update(unchanged=2)):
            old,new=self.fixture();mutate(new)
            self.assertFalse(warning_only_cache_compatible(old,new))
        old,new=self.fixture();old['implementation']['/report/position_search.py']='unknown'
        self.assertFalse(warning_only_cache_compatible(old,new))
