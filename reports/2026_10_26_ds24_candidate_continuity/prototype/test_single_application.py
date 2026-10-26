import json
import unittest
import experiment as e
import single_application as s


class ThinApplicationTests(unittest.TestCase):
    def test_normalizer_exact_original_port_on_archived_control(self):
        port=json.loads((e.HERE/'prepared/synthetic_rows.json').read_text())
        episode=port['episodes'][0]
        slot=json.loads((e.OLD/'slots'/f"{episode['name']}_00.json").read_text())
        for rx in slot['receivers']:
            actual=s.port_window(slot,rx,episode['name'])
            expected=next(w for w in episode['windows'] if w['receiver_id']==str(rx['receiver_id']) and w['window_start_counter']==0)
            self.assertEqual(actual,expected)
            self.assertFalse(any('source' in k for k in actual))


if __name__=='__main__':unittest.main()
