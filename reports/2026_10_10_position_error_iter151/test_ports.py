import unittest
from ports import PARENT,search_source,continuation_source,replace_once,native_score

class SourceTests(unittest.TestCase):
    def test_two_native_arm_queues_no_rescore(self):
        text=search_source((PARENT/'search.py').read_text())
        compile(text,'search151','exec')
        self.assertIn('else "zero-c"',text)
        self.assertNotIn('for mode in ("native", "fixed")',text)
        self.assertEqual(native_score(None,None,None,123),{'native':{'objective':123}})
    def test_continuation_uses_own_arm_and_handoff(self):
        text=continuation_source((PARENT/'continuation.py').read_text());compile(text,'continue151','exec')
        self.assertIn('else "zero-c"',text);self.assertIn('RECOVERY_PORT',text)
        self.assertIn('local_radius_km=25.0',text)
    def test_source_shapes_reject_silent_changes(self):
        with self.assertRaises(ValueError):replace_once('wrong','expected','new')
        with self.assertRaises(ValueError):replace_once('old old','old','new')

if __name__=='__main__':unittest.main()
