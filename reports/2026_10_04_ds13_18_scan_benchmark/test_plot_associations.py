import unittest
from types import SimpleNamespace
import numpy as np
from plot_associations import display_rows


class PlotAccountingTests(unittest.TestCase):
    def test_selected_alternative_replaces_top_without_inflating_count(self):
        d=SimpleNamespace(group=np.array([0,0,1,1,2]),top_mask=np.array([True,False,True,False,True]))
        rows=display_rows(d,[{'row_index':1},{'row_index':2}])
        self.assertEqual(rows.tolist(),[1,2,4])

    def test_duplicate_window_assignment_is_rejected(self):
        d=SimpleNamespace(group=np.array([0,0]),top_mask=np.array([True,False]))
        with self.assertRaises(ValueError):
            display_rows(d,[{'row_index':0},{'row_index':1}])
